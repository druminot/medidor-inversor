#ifndef LOGGER_H
#define LOGGER_H

#include <stdio.h>
#include <stdarg.h>
#include <time.h>

#define LOG_COLOR_RED     "\033[31m"
#define LOG_COLOR_YELLOW  "\033[33m"
#define LOG_COLOR_GREEN   "\033[32m"
#define LOG_COLOR_RESET   "\033[0m"

static inline void log_timestamp(void) {
    char buf[32];
    time_t now = time(NULL);
    struct tm *tm_info = gmtime(&now);
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", tm_info);
    fprintf(stdout, "[%s] ", buf);
}

#define log_error(fmt, ...) do { \
    log_timestamp(); \
    fprintf(stdout, LOG_COLOR_RED "ERROR " LOG_COLOR_RESET fmt "\n", ##__VA_ARGS__); \
    fflush(stdout); \
} while (0)

#define log_warn(fmt, ...) do { \
    log_timestamp(); \
    fprintf(stdout, LOG_COLOR_YELLOW "WARN  " LOG_COLOR_RESET fmt "\n", ##__VA_ARGS__); \
    fflush(stdout); \
} while (0)

#define log_info(fmt, ...) do { \
    log_timestamp(); \
    fprintf(stdout, LOG_COLOR_GREEN "INFO  " LOG_COLOR_RESET fmt "\n", ##__VA_ARGS__); \
    fflush(stdout); \
} while (0)

#define log_read(fmt, ...) do { \
    log_timestamp(); \
    fprintf(stdout, "READ  " fmt "\n", ##__VA_ARGS__); \
    fflush(stdout); \
} while (0)

#endif /* LOGGER_H */