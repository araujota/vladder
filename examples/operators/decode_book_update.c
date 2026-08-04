#include <stddef.h>
#include <stdint.h>

#define BOOK_LEVELS 64
#define PRICE_BASE 100000

typedef struct {
    int32_t bid_qty[BOOK_LEVELS];
    int32_t ask_qty[BOOK_LEVELS];
    uint64_t last_sequence;
    int32_t best_bid_level;
    int32_t best_ask_level;
    uint64_t bid_occupied;
    uint64_t ask_occupied;
} BookState;

typedef struct {
    uint8_t type;
    uint8_t side;
    int32_t price_ticks;
    int32_t quantity;
    uint64_t sequence;
} NormalizedEvent;

typedef struct {
    int32_t best_bid_ticks;
    int32_t best_bid_qty;
    int32_t best_ask_ticks;
    int32_t best_ask_qty;
} TopOfBook;

void decode_book_update(
    const uint8_t *message,
    size_t length,
    BookState *book,
    NormalizedEvent *event_out,
    TopOfBook *top_out,
    uint64_t *changed_mask_out,
    int32_t *status_out) {
    if (length != 18) {
        *status_out = -1;
        *changed_mask_out = 0;
        return;
    }
    NormalizedEvent event;
    event.type = message[0];
    event.side = message[1];
    event.price_ticks = (int32_t)(((uint32_t)message[2] << 24) | ((uint32_t)message[3] << 16) |
                                  ((uint32_t)message[4] << 8) | (uint32_t)message[5]);
    event.quantity = (int32_t)(((uint32_t)message[6] << 24) | ((uint32_t)message[7] << 16) |
                               ((uint32_t)message[8] << 8) | (uint32_t)message[9]);
    event.sequence = 0;
    for (size_t i = 10; i < 18; ++i) {
        event.sequence = (event.sequence << 8) | message[i];
    }
    if (event.type < 1 || event.type > 3 || event.side > 1 ||
        event.price_ticks < PRICE_BASE || event.price_ticks >= PRICE_BASE + BOOK_LEVELS ||
        event.quantity < 0 || event.sequence <= book->last_sequence) {
        *status_out = -2;
        *changed_mask_out = 0;
        return;
    }
    size_t level = (size_t)(event.price_ticks - PRICE_BASE);
    int32_t quantity = event.type == 3 ? 0 : event.quantity;
    if (event.side == 0) {
        book->bid_qty[level] = quantity;
        if (quantity) book->bid_occupied |= UINT64_C(1) << level;
        else book->bid_occupied &= ~(UINT64_C(1) << level);
    } else {
        book->ask_qty[level] = quantity;
        if (quantity) book->ask_occupied |= UINT64_C(1) << level;
        else book->ask_occupied &= ~(UINT64_C(1) << level);
    }
    book->last_sequence = event.sequence;
    *event_out = event;
    *changed_mask_out = UINT64_C(1) << level;

    top_out->best_bid_ticks = 0;
    top_out->best_bid_qty = 0;
    for (size_t i = BOOK_LEVELS; i-- > 0;) {
        if (book->bid_qty[i] > 0) {
            top_out->best_bid_ticks = PRICE_BASE + (int32_t)i;
            top_out->best_bid_qty = book->bid_qty[i];
            book->best_bid_level = (int32_t)i;
            break;
        }
    }
    if (top_out->best_bid_ticks == 0) book->best_bid_level = -1;
    top_out->best_ask_ticks = 0;
    top_out->best_ask_qty = 0;
    for (size_t i = 0; i < BOOK_LEVELS; ++i) {
        if (book->ask_qty[i] > 0) {
            top_out->best_ask_ticks = PRICE_BASE + (int32_t)i;
            top_out->best_ask_qty = book->ask_qty[i];
            book->best_ask_level = (int32_t)i;
            break;
        }
    }
    if (top_out->best_ask_ticks == 0) book->best_ask_level = -1;
    *status_out = 0;
}
