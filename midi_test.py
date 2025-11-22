import pygame.midi
import time

def list_midi_devices():
    pygame.midi.init()
    print("--- Detected MIDI Input Devices ---")
    
    found_devices = False
    for i in range(pygame.midi.get_count()):
        info = pygame.midi.get_device_info(i)
        if info[2] == 1:  # Input device
            print(f"ID: {i} | Name: {info[1].decode('utf-8')}")
            found_devices = True
            
    if not found_devices:
        print("No MIDI input devices found.")
        
    print("---------------------------------")
    return found_devices

def monitor_device(device_id):
    print(f"\nMonitoring device ID: {device_id}. Press Ctrl+C to exit.")
    try:
        midi_input = pygame.midi.Input(device_id)
        while True:
            if midi_input.poll():
                events = midi_input.read(16)
                for event in events:
                    print(f"MIDI Event: {event}")
            time.sleep(0.01)
    except (pygame.midi.MidiException, KeyboardInterrupt) as e:
        print(f"\nExiting monitor. ({e})")
    finally:
        if 'midi_input' in locals() and midi_input:
            midi_input.close()
        pygame.midi.quit()

if __name__ == "__main__":
    if list_midi_devices():
        try:
            device_id_str = input("Enter the ID of your MIDI keyboard to monitor it: ")
            device_id = int(device_id_str)
            monitor_device(device_id)
        except (ValueError, EOFError):
            print("Invalid input. Exiting.")
    
    pygame.midi.quit()

