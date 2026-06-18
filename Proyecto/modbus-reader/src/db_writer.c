#include "db_writer.h"
#include "logger.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static const char *table_name_from_enum(target_table_t table) {
    switch (table) {
        case TABLE_REALTIME:          return "realtime";
        case TABLE_FAST_SAMPLES:      return "fast_samples";
        case TABLE_CUMULATIVES:       return "cumulatives";
        case TABLE_DAILY_PRODUCTION:  return "daily_production";
        default:                       return NULL;
    }
}

static int is_allowed_column(const char *name) {
    static const char *allowed_columns[] = {
        "temperature", "power_ac", "status",
        "vpv", "ipv", "vac", "iac", "fac", "power_dc",
        "energy_total", "energy_daily", "hours_total", "co2_saved",
        "daily_graph",
        NULL
    };
    for (int i = 0; allowed_columns[i] != NULL; i++) {
        if (strcmp(name, allowed_columns[i]) == 0) return 1;
    }
    return 0;
}

static void iso8601_now(char *buf, size_t len) {
    time_t now = time(NULL);
    struct tm *tm_info = gmtime(&now);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%S", tm_info);
}

db_writer_t *db_writer_init(const config_t *cfg) {
    db_writer_t *db = malloc(sizeof(db_writer_t));
    if (db == NULL) {
        log_error("Failed to allocate db_writer");
        return NULL;
    }

    db->conn = NULL;
    db->connected = 0;
    db->buffer_count = 0;
    db->buffer_size = cfg->buffer_size;
    db->total_inserts = 0;
    db->total_errors = 0;

    db->buffer = malloc(sizeof(buffer_entry_t) * db->buffer_size);
    if (db->buffer == NULL) {
        log_error("Failed to allocate buffer (%d entries)", db->buffer_size);
        free(db);
        return NULL;
    }

    snprintf(db->conninfo, sizeof(db->conninfo),
             "host=%s port=%d dbname=%s user=%s password=%s",
             cfg->db_host, cfg->db_port, cfg->db_name,
             cfg->db_user, cfg->db_password);

    return db;
}

int db_writer_connect(db_writer_t *db) {
    if (db->connected) return 0;

    db->conn = PQconnectdb(db->conninfo);
    if (PQstatus(db->conn) != CONNECTION_OK) {
        log_error("DB connection failed: %s", PQerrorMessage(db->conn));
        PQfinish(db->conn);
        db->conn = NULL;
        db->connected = 0;
        return -1;
    }

    db->connected = 1;
    log_info("Connected to TimescaleDB: %s:%s/%s",
             PQhost(db->conn), PQport(db->conn), PQdb(db->conn));

    if (db->buffer_count > 0) {
        log_info("Flushing %d buffered entries", db->buffer_count);
        db_writer_flush_buffer(db);
    }

    return 0;
}

void db_writer_disconnect(db_writer_t *db) {
    if (db->conn != NULL && db->connected) {
        PQfinish(db->conn);
        db->conn = NULL;
        db->connected = 0;
        log_info("Disconnected from TimescaleDB");
    }
}

void db_writer_free(db_writer_t *db) {
    if (db == NULL) return;
    db_writer_disconnect(db);
    if (db->buffer != NULL) free(db->buffer);
    free(db);
}

static int db_exec_insert(db_writer_t *db, const char *query, int nparams,
                          const char **param_values, const int *param_lengths,
                          const int *param_formats) {
    if (!db->connected) return -1;

    PGresult *res = PQexecParams(db->conn, query, nparams, NULL,
                                  param_values, param_lengths, param_formats, 0);
    if (PQresultStatus(res) != PGRES_COMMAND_OK &&
        PQresultStatus(res) != PGRES_TUPLES_OK) {
        log_error("DB insert error: %s", PQerrorMessage(db->conn));
        PQclear(res);
        db->total_errors++;
        db->connected = 0;
        PQfinish(db->conn);
        db->conn = NULL;
        return -1;
    }

    PQclear(res);
    db->total_inserts++;
    return 0;
}

int db_writer_insert(db_writer_t *db, target_table_t table,
                     const char *name, float value,
                     const char *unit, int inverter_id) {
    char timestamp[32];
    iso8601_now(timestamp, sizeof(timestamp));

    if (!is_allowed_column(name)) {
        log_error("Rejected unknown column name: %s", name);
        return -1;
    }

    const char *table_name = table_name_from_enum(table);
    if (table_name == NULL) {
        log_error("Rejected unknown table enum: %d", table);
        return -1;
    }

    if (!db->connected) {
        if (db->buffer_count >= db->buffer_size) {
            log_warn("Buffer full (%d entries), dropping oldest", db->buffer_size);
            memmove(db->buffer, db->buffer + 1,
                    sizeof(buffer_entry_t) * (db->buffer_size - 1));
            db->buffer_count = db->buffer_size - 1;
        }

        buffer_entry_t *entry = &db->buffer[db->buffer_count++];
        entry->table = table;
        strncpy(entry->name, name, sizeof(entry->name) - 1);
        entry->name[sizeof(entry->name) - 1] = '\0';
        entry->value = value;
        strncpy(entry->unit, unit, sizeof(entry->unit) - 1);
        entry->unit[sizeof(entry->unit) - 1] = '\0';
        strncpy(entry->timestamp, timestamp, sizeof(entry->timestamp) - 1);
        entry->timestamp[sizeof(entry->timestamp) - 1] = '\0';
        return 0;
    }

    char val_str[32];
    snprintf(val_str, sizeof(val_str), "%.4f", value);

    char inv_str[8];
    snprintf(inv_str, sizeof(inv_str), "%d", inverter_id);

    char query[512];

    if (table == TABLE_REALTIME) {
        snprintf(query, sizeof(query),
            "INSERT INTO %s (time, inverter_id, %s) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (inverter_id) DO UPDATE SET %s = EXCLUDED.%s, time = EXCLUDED.time",
            table_name, name, name, name);
    } else {
        snprintf(query, sizeof(query),
            "INSERT INTO %s (time, inverter_id, %s) "
            "VALUES ($1, $2, $3)",
            table_name, name);
    }

    const char *param_values[3] = {timestamp, inv_str, val_str};
    int param_lengths[3] = {0, 0, 0};
    int param_formats[3] = {0, 0, 0};

    int rc = db_exec_insert(db, query, 3, param_values,
                            param_lengths, param_formats);
    if (rc == 0) {
        log_read("%s: %s=%s%s", table_name, name, val_str, unit);
    }

    return rc;
}

int db_writer_flush_buffer(db_writer_t *db) {
    if (!db->connected || db->buffer_count == 0) return 0;

    int flushed = 0;
    int original_count = db->buffer_count;

    for (int i = 0; i < original_count; i++) {
        buffer_entry_t *entry = &db->buffer[i];
        if (db_writer_insert(db, entry->table, entry->name,
                              entry->value, entry->unit, 1) == 0) {
            flushed++;
        } else {
            break;
        }
    }

    int remaining = original_count - flushed;
    if (remaining > 0) {
        memmove(db->buffer, db->buffer + flushed,
                sizeof(buffer_entry_t) * remaining);
    }
    db->buffer_count = remaining;

    log_info("Flushed %d/%d buffered entries to DB", flushed, original_count);
    return flushed;
}

int db_writer_insert_event(db_writer_t *db, const char *event_type,
                            const char *event_value, int severity,
                            int inverter_id) {
    char timestamp[32];
    iso8601_now(timestamp, sizeof(timestamp));

    char inv_str[8], sev_str[8];
    snprintf(inv_str, sizeof(inv_str), "%d", inverter_id);
    snprintf(sev_str, sizeof(sev_str), "%d", severity);

    const char *query = "INSERT INTO events (time, inverter_id, event_type, "
                        "event_value, severity) VALUES ($1, $2, $3, $4, $5)";

    const char *param_values[5] = {timestamp, inv_str, event_type,
                                    event_value, sev_str};
    int param_lengths[5] = {0, 0, 0, 0, 0};
    int param_formats[5] = {0, 0, 0, 0, 0};

    return db_exec_insert(db, query, 5, param_values,
                          param_lengths, param_formats);
}