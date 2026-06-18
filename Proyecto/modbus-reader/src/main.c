#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>

#include "config.h"
#include "logger.h"
#include "modbus_comm.h"
#include "db_writer.h"
#include "register_map.h"
#include "watchdog.h"

static volatile sig_atomic_t running = 1;
static volatile sig_atomic_t flush_buffer = 0;

static void signal_handler(int sig) {
    if (sig == SIGTERM || sig == SIGINT) {
        log_info("Received signal %d, shutting down...", sig);
        running = 0;
    } else if (sig == SIGUSR1) {
        flush_buffer = 1;
    }
}

int main(int argc, char *argv[]) {
    (void)argc;
    (void)argv;
    log_info("modbus-reader starting...");

    /* Setup signal handlers */
    struct sigaction sa;
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGUSR1, &sa, NULL);

    /* Load configuration */
    config_t *cfg = config_from_env();
    if (cfg == NULL) {
        log_error("Failed to load configuration");
        return 1;
    }

    /* Initialize watchdog */
    watchdog_init();
    watchdog_status_t wd_status = {0};
    wd_status.start_time = time(NULL);

    /* Initialize DB writer */
    db_writer_t *db = db_writer_init(cfg);
    if (db == NULL) {
        log_error("Failed to initialize DB writer");
        config_free(cfg);
        return 1;
    }

    /* Main connection/reconnection loop */
    modbus_comm_t *mc = NULL;
    time_t last_realtime = 0;
    time_t last_fast = 0;
    time_t last_watchdog = 0;
    int readings_this_cycle = 0;
    int backoff_wait = 5;

    while (running) {
        /* Initialize Modbus communication if needed */
        if (mc == NULL) {
            mc = modbus_comm_init(cfg);
            if (mc == NULL) {
                log_error("Failed to create Modbus context, retrying in %ds...", backoff_wait);
                sleep(backoff_wait);
                backoff_wait = backoff_wait < 300 ? backoff_wait * 2 : 300;
                continue;
            }
            backoff_wait = 5;
        }

        /* Connect if not connected */
        if (!mc->connected) {
            if (modbus_comm_connect(mc) != 0) {
                int wait = modbus_comm_backoff_get(mc);
                log_error("Connection failed, retrying in %ds...", wait);
                modbus_comm_free(mc);
                mc = NULL;
                sleep(wait);
                continue;
            }

            /* Unlock the inverter protocol */
            if (modbus_comm_unlock(mc) != 0) {
                log_error("Unlock failed, reconnecting...");
                int wait = modbus_comm_backoff_get(mc);
                modbus_comm_disconnect(mc);
                modbus_comm_free(mc);
                mc = NULL;
                sleep(wait);
                continue;
            }

            modbus_comm_backoff_reset(mc);
            log_info("Connected and unlocked successfully");
        }

        /* Connect to DB if not connected */
        if (!db->connected) {
            if (db_writer_connect(db) != 0) {
                log_error("DB connection failed, buffering data");
            }
        }

        /* Flush buffer if signaled */
        if (flush_buffer && db->connected) {
            db_writer_flush_buffer(db);
            flush_buffer = 0;
        }

        time_t now = time(NULL);

        /* === Realtime readings (every poll_realtime seconds) === */
        if ((now - last_realtime) >= cfg->poll_realtime) {
            readings_this_cycle = 0;

            for (int i = 0; i < register_map_size; i++) {
                const register_entry_t *reg = &register_map[i];

                if (reg->address == 0x0000) continue;
                if (reg->table != TABLE_REALTIME) continue;
                if (reg->count >= 10) continue;

                uint16_t dest[2] = {0};
                int rc = modbus_comm_read(mc, reg->address, reg->count, dest);

                if (rc == -2) {
                    db_writer_insert_event(db, "connection",
                                          "modbus_disconnected", 2, 1);
                    break;
                } else if (rc == -1) {
                    wd_status.errors_total++;
                    continue;
                }

                float value;
                if (reg->count == 2) {
                    value = (float)((dest[1] << 16) | dest[0]) * reg->scale;
                } else {
                    value = (float)dest[0] * reg->scale;
                }

                db_writer_insert(db, reg->table, reg->name,
                                  value, reg->unit, 1);
                readings_this_cycle++;
            }

            if (readings_this_cycle > 0) {
                wd_status.readings_total += readings_this_cycle;
                last_realtime = now;
            }
        }

        /* === Fast samples (every poll_fast seconds) === */
        if ((now - last_fast) >= cfg->poll_fast) {
            for (int i = 0; i < register_map_size; i++) {
                const register_entry_t *reg = &register_map[i];

                if (reg->address == 0x0000) continue;
                if (reg->table != TABLE_FAST_SAMPLES &&
                    reg->table != TABLE_CUMULATIVES) continue;
                if (reg->count >= 10) continue;

                uint16_t dest[2] = {0};
                int rc = modbus_comm_read(mc, reg->address, reg->count, dest);

                if (rc == -2) {
                    db_writer_insert_event(db, "connection",
                                          "modbus_disconnected", 2, 1);
                    break;
                } else if (rc == -1) {
                    wd_status.errors_total++;
                    continue;
                }

                float value;
                if (reg->count == 2) {
                    value = (float)((dest[1] << 16) | dest[0]) * reg->scale;
                } else {
                    value = (float)dest[0] * reg->scale;
                }

                db_writer_insert(db, reg->table, reg->name,
                                  value, reg->unit, 1);
                wd_status.readings_total++;
            }

            last_fast = now;
        }

        /* === Update watchdog (every 30 seconds) === */
        if ((now - last_watchdog) >= 30) {
            wd_status.modbus_connected = mc ? mc->connected : 0;
            wd_status.db_connected = db->connected;
            wd_status.buffer_size = db->buffer_count;
            watchdog_update(&wd_status);
            last_watchdog = now;
        }

        /* === Sleep until next cycle === */
        sleep(1);
    }

    /* === Graceful shutdown === */
    log_info("Shutting down...");

    if (db->connected && db->buffer_count > 0) {
        log_info("Flushing %d remaining entries before exit...",
                 db->buffer_count);
        db_writer_flush_buffer(db);
    }

    watchdog_cleanup();
    db_writer_free(db);

    if (mc != NULL) {
        modbus_comm_disconnect(mc);
        modbus_comm_free(mc);
    }

    config_free(cfg);
    log_info("modbus-reader stopped.");
    return 0;
}