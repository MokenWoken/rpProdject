import pygame, random, json, time, atexit, os, sys
from evdev import InputDevice, list_devices, categorize, ecodes

# --- Init mixer (tuned for Pi 1B) ---
pygame.mixer.pre_init(22050, -16, 1, 256)
pygame.init()
pygame.mixer.init()

# --- Utility functions ---
def play(sound_or_list, block=True):
    """Play one sound (or random from a list). Blocks unless block=False."""
    sound = random.choice(sound_or_list) if isinstance(sound_or_list, list) else sound_or_list
    ch = sound.play()
    if block and ch is not None:
        while ch.get_busy():
            pygame.time.delay(10)

def load_sound_list(filenames):
    """Load .wav files into pygame Sound objects."""
    return [pygame.mixer.Sound(f) for f in filenames]

# --- Enhanced keyboard handling ---
def find_keyboards():
    """Find all keyboard-like devices and return them sorted by preference."""
    devices = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            
            # Must have key events
            if ecodes.EV_KEY not in caps:
                continue
                
            name = dev.name.lower()
            print(f"Found input device: {dev.name} ({path})")
            
            # Skip virtual, HDMI audio, GPIO devices
            if any(skip in name for skip in ["vc4-hdmi", "gpio", "virtual", "bcm2835"]):
                print(f"  -> Skipped (virtual/system device)")
                continue
                
            # Check if it has keyboard-like keys
            key_caps = caps.get(ecodes.EV_KEY, [])
            has_letters = any(code in key_caps for code in [
                ecodes.KEY_A, ecodes.KEY_B, ecodes.KEY_C, ecodes.KEY_D, ecodes.KEY_E
            ])
            has_numbers = any(code in key_caps for code in [
                ecodes.KEY_1, ecodes.KEY_2, ecodes.KEY_3, ecodes.KEY_4, ecodes.KEY_5
            ])
            
            if has_letters or has_numbers:
                # Prefer USB keyboards over others
                priority = 1 if "usb" in name else 2
                devices.append((priority, dev, path))
                print(f"  -> Added as keyboard candidate (priority {priority})")
            else:
                print(f"  -> Skipped (no keyboard keys)")
                
        except Exception as e:
            print(f"Error checking device {path}: {e}")
            continue
    
    # Sort by priority (lower number = higher priority)
    devices.sort(key=lambda x: x[0])
    return [dev for _, dev, _ in devices]

def open_keyboard():
    """Find and open the first real keyboard device and grab it exclusively."""
    keyboards = find_keyboards()
    
    for dev in keyboards:
        try:
            print(f"Attempting to grab: {dev.name} ({dev.path})")
            
            # Add delay before grabbing as suggested in research
            time.sleep(0.1)
            
            # Try to grab exclusive access
            dev.grab()
            print(f"  -> Successfully grabbed!")
            
            # Test that we can read from it
            dev.set_absinfo(ecodes.ABS_X, (0, 100, 0, 0, 0, 0))  # This will fail if not a real device
            
            return dev
            
        except OSError as e:
            print(f"  -> Failed to grab ({e})")
            try:
                dev.close()
            except:
                pass
            continue
        except Exception as e:
            print(f"  -> Error: {e}")
            try:
                dev.ungrab()
                dev.close()
            except:
                pass
            continue
    
    return None

def release_keyboard(dev):
    """Safely release keyboard grab."""
    if dev:
        try:
            print(f"Releasing keyboard: {dev.name}")
            dev.ungrab()
            dev.close()
        except Exception as e:
            print(f"Error releasing keyboard: {e}")

def get_key_event(dev):
    """Block until a key press event is read, return a lowercase key string."""
    try:
        for event in dev.read_loop():
            if event.type == ecodes.EV_KEY:
                key_event = categorize(event)
                if key_event.keystate == key_event.key_down:
                    code = key_event.keycode
                    if isinstance(code, list):   # sometimes a list
                        code = code[0]
                    if code.startswith("KEY_"):
                        return code[4:].lower()
                    return code.lower()
    except OSError:
        # device disappeared
        raise RuntimeError("KeyboardDisconnected")

def wait_for_keyboard():
    """Block until a real keyboard is connected and return the device."""
    print("Waiting for keyboard...")
    kb = None
    attempt = 0
    while not kb:
        attempt += 1
        print(f"Attempt {attempt}...")
        
        kb = open_keyboard()
        if not kb:
            print("No keyboard found, waiting 2 seconds...")
            time.sleep(2)
        else:
            print(f"Keyboard ready: {kb.name} ({kb.path})")
    
    return kb

# Check if running as root (may be required for grabbing)
if os.geteuid() != 0:
    print("WARNING: Not running as root. If keyboard grab fails, try:")
    print("  sudo python3 your_script.py")
    print("  or add your user to the 'input' group:")
    print("  sudo usermod -a -G input $USER")
    print()

# --- Load stage data ---
with open("stages.json", "r") as f:
    stages_data = json.load(f)

stages_by_id = {}
stage_order = []
for s in stages_data:
    stage = {
        "id": s["id"],
        "prompt": load_sound_list(s["prompt"]),
        "correct": s["correct"],
        "success": load_sound_list(s["success"]),
        "fail": {k.lower(): load_sound_list(v) for k, v in s.get("fail", {}).items()},
        "fail_default": load_sound_list(s.get("fail_default", [])),
        "next_on_success": s.get("next_on_success"),
        "next_on_fail": s.get("next_on_fail"),
        "fail_branches": s.get("fail_branches", {})
    }
    stages_by_id[stage["id"]] = stage
    stage_order.append(stage["id"])

# --- Load keypress sounds ---
with open("keypress.json", "r") as f:
    kp_data = json.load(f)

keypress_sounds = {
    k.lower(): load_sound_list(v)
    for k, v in kp_data.get("keypress_sounds", {}).items()
}
keypress_fallback = load_sound_list(kp_data.get("keypress_fallback", []))

keypress_sounds_channel = pygame.mixer.Channel(2)

def play_keypress_sound(key):
    """Play a random sound for this key on the keypress channel."""
    if key in keypress_sounds:
        sound = random.choice(keypress_sounds[key])
    else:
        sound = random.choice(keypress_fallback)
    keypress_sounds_channel.play(sound)

# --- Global sounds ---
beep = pygame.mixer.Sound("beep.wav")
buzzer = pygame.mixer.Sound("buzzer.wav")
bg_music = pygame.mixer.Sound("background.wav")
keyboard_connected_sound = pygame.mixer.Sound("keyboard_connected.wav")

music_channel = pygame.mixer.Channel(0)
sfx_channel = pygame.mixer.Channel(1)

# --- Stage runner ---
def run_stages(kb):
    current_stage_id = stage_order[0]

    while current_stage_id:
        stage = stages_by_id[current_stage_id]
        play(stage["prompt"])

        fail_counters = {k: 0 for k in stage["fail"]}
        default_fail_counter = 0
        fail_count = 0
        next_stage_id = None
        correct_def = stage["correct"]

        # --- Case: sequence of keys ---
        if isinstance(correct_def, list) and len(correct_def) > 0 and isinstance(correct_def[0], list):
            sequence = [k.lower() for k in correct_def[0]]
            seq_index = 0
            while seq_index < len(sequence):
                key = get_key_event(kb)
                play_keypress_sound(key)
                if key == sequence[seq_index]:
                    play(beep, block=False)
                    seq_index += 1
                else:
                    play(buzzer)
                    if stage["fail_default"]:
                        idx = default_fail_counter
                        sounds = stage["fail_default"]
                        play(sounds[idx])
                        if idx < len(sounds) - 1:
                            default_fail_counter += 1
                    print("Wrong key in sequence, restarting...")
                    seq_index = 0
            play(stage["success"])
            print("Sequence completed!")
            next_stage_id = stage.get("next_on_success")

        # --- Case: normal ---
        else:
            while True:
                key = get_key_event(kb)
                play_keypress_sound(key)

                correct_keys = correct_def
                if isinstance(correct_keys, str):
                    correct_keys = [correct_keys]
                correct_keys = [ck.lower() for ck in correct_keys]

                if key in correct_keys:
                    play(beep, block=False)
                    play(stage["success"])
                    print("Correct!")
                    next_stage_id = stage.get("next_on_success")
                    break
                else:
                    fail_count += 1
                    if key in stage["fail"]:
                        play(buzzer)
                        sounds = stage["fail"][key]
                        idx = fail_counters[key]
                        play(sounds[idx])
                        if idx < len(sounds) - 1:
                            fail_counters[key] += 1
                        print(f"Wrong key '{key}', try again...")
                    elif stage["fail_default"]:
                        play(buzzer)
                        sounds = stage["fail_default"]
                        idx = default_fail_counter
                        play(sounds[idx])
                        if idx < len(sounds) - 1:
                            default_fail_counter += 1
                        print(f"Unexpected key '{key}', fallback fail triggered.")
                    else:
                        play(buzzer)
                        print(f"Unexpected key '{key}', no fail sounds defined.")

                    # --- check fail_branches ---
                    fb = stage.get("fail_branches", {})
                    if str(fail_count) in fb:
                        branch_def = fb[str(fail_count)]
                        print("Special branch triggered. Waiting for input...")
                        branch_key = get_key_event(kb)
                        if branch_key in branch_def["keys"]:
                            next_stage_id = branch_def["keys"][branch_key]
                            break
                        else:
                            print(f"No branch for '{branch_key}', continuing fails...")

                    # --- optional direct fail jump ---
                    if "next_on_fail" in stage and stage["next_on_fail"]:
                        next_stage_id = stage["next_on_fail"]
                        break

        # --- Move to next stage ---
        if not next_stage_id:
            current_index = stage_order.index(stage["id"])
            if current_index + 1 < len(stage_order):
                next_stage_id = stage_order[current_index + 1]
            else:
                next_stage_id = None

        current_stage_id = next_stage_id

# --- Main controller ---
kb = None
try:
    while True:
        if kb:
            release_keyboard(kb)
            kb = None
            
        kb = wait_for_keyboard()
        atexit.register(release_keyboard, kb)

        # Feedback + fade in music
        sfx_channel.play(keyboard_connected_sound)
        music_channel.play(bg_music, loops=-1, fade_ms=2000)
        time.sleep(2)

        try:
            run_stages(kb)
            print("Game finished!")
            break
        except RuntimeError as e:
            if str(e) == "KeyboardDisconnected":
                print("Keyboard disconnected! Restarting from stage 1...")
                music_channel.fadeout(2000)
                continue
            else:
                raise
        except KeyboardInterrupt:
            print("\nShutting down...")
            break
            
finally:
    if kb:
        release_keyboard(kb)
    pygame.quit()
