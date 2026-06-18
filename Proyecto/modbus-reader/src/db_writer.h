#ifndef DB_WRITER_H
#define DB_WRITER_H

#include <libpq-fe.h>
#include "config.h"
#include "register_map.h"

#define BUFFER_MAX_SIZE 1000

typedef struct {
    target_table_t table;
    char name[64];
    float value;
    char unit[16];
    char timestamp[32];
} buffer_entry_t;

typedef struct {
    PGconn *conn;
    int connected;
    char conninfo[512];
    buffer_entry_t *buffer;
    int buffer_count;
    int buffer_size;
    long total_inserts;
    long total_errors;
} db_writer_t;

db_writer_t *db_writer_init(const config_t *cfg);
int db_writer_connect(db_writer_t *db);
void db_writer_disconnect(db_writer_t *db);
void db_writer_free(db_writer_t *db);

int db_writer_insert(db_writer_t *db, target_table_t table,
                     const char *name, float value,
                     const char *unit, int inverter_id);
int db_writer_flush_buffer(db_writer_t *db);
int db_writer_insert_event(db_writer_t *db, const char *event_type,
                            const char *event_value, int severity,
                            int inverter_id);

#endif /* DB_WRITER_H */