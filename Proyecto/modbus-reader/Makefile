CC = gcc
CFLAGS = -Wall -Wextra -O2 -I/usr/include/postgresql -I/usr/include/modbus -I/opt/homebrew/opt/libpq/include -I/opt/homebrew/opt/libmodbus/include
LDFLAGS = -lmodbus -lpq -L/opt/homebrew/opt/libpq/lib -L/opt/homebrew/opt/libmodbus/lib

SRCS = src/main.c src/modbus_comm.c src/db_writer.c src/register_map.c src/config.c src/watchdog.c
OBJS = $(SRCS:.c=.o)
TARGET = modbus-reader

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(OBJS) -o $(TARGET) $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean