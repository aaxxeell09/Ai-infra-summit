// Inspection Station Client - MCU side for Arduino UNO Q (ABX00162).
//
// Owns operator controls (Modulino Buttons, Knob) and all result
// indication: Modulino Pixels, Vibro (transition only), and the onboard
// 8x13 LED matrix (primary fallback; always present on UNO Q).
//
// Python calls:
//   set_status(status, ttl_ms) - 0 IDLE, 1 INSPECTING, 2 OK, 3 CHECK,
//                                4 UNKNOWN; ttl_ms = remaining validity,
//                                Python sends min(hub_expires_in_ms, 3000)
//                                so a dead Python fails fast on the MCU.
//   get_action()               - pop queued button/knob action (0 = none).
//
// Matrix API (verified against installed zephyr 0.56.0 header):
//   int begin(); void setGrayscaleBits(uint8_t); void draw(const uint8_t*);
//   3 grayscale bits -> brightness 0-7. Nonzero byte = lit pixel.
//
// Concurrency: Bridge RPC callbacks run in the library updater thread.
// All RPC state crosses to loop() through ONE packed uint32 word, loaded/
// stored with __atomic builtins (single-copy-atomic on Cortex-M), so there
// are no multi-word volatile races. pending_action is a single aligned
// uint16 - one word, atomic by the same reasoning. All display I2C happens
// only in loop().
//
// Watchdog: deadline = now + ttl_ms at each accepted set_status. loop()
// expires any OK/CHECK/INSPECTING to UNKNOWN when the deadline passes.
// Wrap-safe unsigned millis() arithmetic. A TTL of 0 (hub sent <=10 ms or
// expiry already passed) expires immediately - fail-safe, never extends
// the hub deadline.

#include <Arduino_RouterBridge.h>
#include <Arduino_Modulino.h>
#include <Arduino_LED_Matrix.h>

const uint8_t STATUS_IDLE       = 0;
const uint8_t STATUS_INSPECTING = 1;
const uint8_t STATUS_OK         = 2;
const uint8_t STATUS_CHECK      = 3;
const uint8_t STATUS_UNKNOWN    = 4;

const uint8_t ACTION_NONE    = 0;
const uint8_t ACTION_INSPECT = 1;   // Button A
const uint8_t ACTION_CLEAR   = 2;   // Button B
const uint8_t ACTION_CYCLE   = 3;   // Button C: same as knob clockwise
const uint8_t ACTION_KNOB    = 4;   // knob rotation

ModulinoButtons buttons;
ModulinoPixels pixels;
ModulinoKnob knob;
ModulinoVibro vibro;
Arduino_LED_Matrix matrix;

// ---- module presence (probed in setup; graceful fallback) ----
bool have_buttons = false;
bool have_pixels  = false;
bool have_knob    = false;
bool have_vibro   = false;
bool matrix_ok    = false;

// ---- packed mailbox: one uint32, atomic load/store ----
// bit  0- 2 : status (0-4)
// bit  3-15 : ttl_ms / 10   (0 = expire now; max encoded 81910 ms)
// bit 16    : pending flag (1 = request waiting)
// A request is a single word write; a single word read + flag clear.
static inline uint32_t packReq(uint8_t status, uint32_t ttl_ms) {
  if (ttl_ms > 60000UL) ttl_ms = 60000UL;   // defensive upper cap only
  uint32_t ttl10 = ttl_ms / 10UL;
  return (uint32_t)(status & 0x07) | (ttl10 << 3) | (1UL << 16);
}

uint32_t mailbox = 0;   // accessed only via __atomic builtins
uint32_t displayed_status = STATUS_IDLE; // read-only diagnostic RPC snapshot

uint16_t pending_action = 0;   // single aligned uint16: atomic on ARMv7-M

uint8_t current_status = STATUS_IDLE;
unsigned long status_deadline_ms = 0;

bool pressed_prev[3] = {false, false, false};
unsigned long last_anim_ms = 0;
uint8_t anim_pos = 0;

const uint8_t COL_IDLE[3]  = {40, 40, 40};
const uint8_t COL_PROG[3]  = {0, 0, 150};
const uint8_t COL_OK[3]    = {0, 150, 0};
const uint8_t COL_CHECK[3] = {150, 0, 0};
const uint8_t COL_UNK[3]   = {150, 75, 0};

// 8x13 monochrome glyphs, row-major; draw() lights nonzero bytes at the
// configured grayscale (3 bits -> max 7).
const uint8_t GLYPH_IDLE[104] = {
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  7,7,7,7,7,7,7,7,7,7,7,7,7,
};
const uint8_t GLYPH_CHECK[104] = {
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  7,0,0,0,0,0,0,0,0,0,0,0,7,
  7,7,0,0,0,0,0,0,0,0,0,7,7,
  0,7,7,7,7,7,7,7,7,7,7,7,0,
  0,7,7,7,7,7,7,7,7,7,7,7,0,
  0,0,7,7,7,7,7,7,7,7,7,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
};
const uint8_t GLYPH_OK[104] = {
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,7,7,0,0,0,
  0,0,0,0,0,0,0,7,7,7,7,0,0,
  7,0,0,0,0,0,7,7,0,7,7,7,0,
  7,7,0,0,0,7,7,0,0,0,7,7,0,
  7,7,7,7,7,7,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
};
const uint8_t GLYPH_UNK[104] = {
  0,0,7,7,0,0,0,7,7,0,0,0,0,
  0,7,0,0,7,0,7,0,0,7,0,0,0,
  0,0,0,0,0,7,0,0,0,0,0,0,0,
  0,0,0,0,0,7,0,0,0,0,0,0,0,
  0,0,0,0,0,7,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,7,0,0,0,0,0,0,0,
  0,0,0,0,0,7,0,0,0,0,0,0,0,
};
const uint8_t GLYPH_BLANK[104] = {0};

static void setAllPixels(const uint8_t rgb[3], uint8_t brightness);

// ---- matrix: loop() thread only ----
static void matrixDraw(const uint8_t g[104]) {
  matrix.draw(g);   // verified installed API: void draw(const uint8_t*)
}

static void matrixChase(uint8_t pos) {
  uint8_t frame[104];
  memset(frame, 0, sizeof(frame));
  for (uint8_t r = 0; r < 8; r++) {
    frame[r * 13 + pos] = 7;
    frame[r * 13 + ((pos + 5) % 13)] = 3;
  }
  matrix.draw(frame);
}

// Called only from loop(). Applies the full display state.
static void renderStatus(uint8_t s, bool animate_step, uint8_t chase_pos) {
  __atomic_store_n(&displayed_status, (uint32_t)s, __ATOMIC_RELEASE);
  if (have_pixels) {
    switch (s) {
      case STATUS_IDLE:       setAllPixels(COL_IDLE, 10); break;
      case STATUS_OK:         setAllPixels(COL_OK, 40);   break;
      case STATUS_CHECK:      setAllPixels(COL_CHECK, 40);break;
      case STATUS_UNKNOWN:    setAllPixels(COL_UNK, 40);  break;
      case STATUS_INSPECTING:
        if (animate_step) {
          for (uint8_t i = 0; i < 8; i++) {
            if (i == chase_pos) pixels.set(i, COL_PROG[0], COL_PROG[1], COL_PROG[2], 40);
            else                pixels.clear(i);
          }
          pixels.show();
        }
        break;
    }
  }
  if (have_buttons) {
    buttons.setLeds(s == STATUS_IDLE, false, false);   // A indicator = ready
  }
  if (matrix_ok) {
    switch (s) {
      case STATUS_IDLE:       matrixDraw(GLYPH_IDLE);  break;
      case STATUS_INSPECTING: matrixChase(chase_pos);  break;
      case STATUS_OK:         matrixDraw(GLYPH_OK);    break;
      case STATUS_CHECK:      matrixDraw(GLYPH_CHECK); break;
      case STATUS_UNKNOWN:    matrixDraw(GLYPH_UNK);   break;
    }
  }
}

static void setAllPixels(const uint8_t rgb[3], uint8_t brightness) {
  for (uint8_t i = 0; i < 8; i++) {
    pixels.set(i, rgb[0], rgb[1], rgb[2], brightness);
  }
  pixels.show();
}

static void hapticTick() {
  if (have_vibro) vibro.on(120, false, GENTLE);   // non-blocking
}

// ---- Bridge RPC handlers ----
// Pack into one uint32 word and store atomically. No I2C here.
bool set_status(uint8_t status, unsigned long ttl_ms) {
  if (status > STATUS_UNKNOWN) return false;
  // No upward clamp: a small TTL (even 10 ms after /10 packing) expires on
  // schedule. Only a defensive 60 s cap so the bitfield cannot overflow.
  uint32_t word = packReq(status, ttl_ms);
  __atomic_store_n(&mailbox, word, __ATOMIC_RELEASE);
  return true;
}

int get_action() {
  return (int)__atomic_exchange_n(&pending_action, (uint16_t)0, __ATOMIC_ACQ_REL);
}

int get_status() {
  return (int)__atomic_load_n(&displayed_status, __ATOMIC_ACQUIRE);
}

int get_modules() {
  return (have_buttons ? 1 : 0) | (have_pixels ? 2 : 0) |
         (have_knob ? 4 : 0) | (have_vibro ? 8 : 0) | (matrix_ok ? 16 : 0);
}

// Operator input: loop() thread only. Buttons produce a single packed word
// (code only, direction 0); knob packs code + direction in the high byte.
static void queueAction(uint16_t a) {
  __atomic_store_n(&pending_action, a, __ATOMIC_RELEASE);
}

static void readOperatorInput() {
  if (have_buttons && buttons.update()) {
    bool a = buttons.isPressed('A');
    bool b = buttons.isPressed('B');
    bool c = buttons.isPressed('C');
    if (a && !pressed_prev[0]) queueAction(ACTION_INSPECT);
    if (b && !pressed_prev[1]) queueAction(ACTION_CLEAR);
    if (c && !pressed_prev[2]) queueAction(ACTION_CYCLE);
    pressed_prev[0] = a; pressed_prev[1] = b; pressed_prev[2] = c;
  }
  if (have_knob) {
    int8_t dir = knob.getDirection();   // verified: Modulino.h, no update()
    if (dir != 0) queueAction((uint16_t)ACTION_KNOB | ((uint16_t)(uint8_t)dir << 8));
  }
}

void setup() {
  Bridge.begin();
  Modulino.begin(Wire1);   // UNO Q external I2C bus, per official examples

  have_buttons = buttons.begin();
  have_pixels  = pixels.begin();
  have_knob    = knob.begin();
  have_vibro   = vibro.begin();

  // Onboard 8x13 LED matrix (soldered on UNO Q).
  matrix_ok = (matrix.begin() == 1);   // verified: int begin()
  if (matrix_ok) {
    matrix.setGrayscaleBits(3);        // verified: void setGrayscaleBits(uint8_t)
    matrix.draw(GLYPH_BLANK);
  }

  Bridge.provide("set_status", set_status);
  Bridge.provide("get_action", get_action);
  Bridge.provide("get_status", get_status);
  Bridge.provide("get_modules", get_modules);

  renderStatus(STATUS_IDLE, false, 0);
}

void loop() {
  readOperatorInput();

  // Consume one packed RPC request atomically.
  uint32_t word = __atomic_exchange_n(&mailbox, (uint32_t)0, __ATOMIC_ACQ_REL);
  if (word & (1UL << 16)) {
    uint8_t s = word & 0x07;
    uint32_t ttl_ms = ((word >> 3) & 0x1FFF) * 10UL;

    bool transition = (s != current_status);
    current_status = s;
    status_deadline_ms = millis() + ttl_ms;   // wrap-safe
    renderStatus(current_status, transition, 0);
    // Vibro only on a real status transition, never on unchanged refresh.
    if (transition && s != STATUS_IDLE) hapticTick();
  }

  // Watchdog: expire current status when the TTL passes.
  if (current_status != STATUS_IDLE && current_status != STATUS_UNKNOWN) {
    if ((long)(millis() - status_deadline_ms) >= 0) {
      current_status = STATUS_UNKNOWN;
      renderStatus(STATUS_UNKNOWN, false, 0);
      hapticTick();
    }
  }

  // INSPECTING chase animation (13 matrix columns).
  if (current_status == STATUS_INSPECTING) {
    unsigned long now = millis();
    if (now - last_anim_ms >= 150) {
      last_anim_ms = now;
      anim_pos = (anim_pos + 1) % 13;
      renderStatus(STATUS_INSPECTING, true, anim_pos);
    }
  } else {
    last_anim_ms = millis();
  }

  delay(10);
}
