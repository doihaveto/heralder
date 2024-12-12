from pydub import AudioSegment
from pydub.silence import detect_silence

def trim_silence(audio):
    silence_threshold = -50  # dB, adjust this based on your file's noise floor
    silence_chunk_len = 50  # Minimum length of silence to detect, in milliseconds
    # Detect non-silent segments (returns a list of (start, end) in ms)
    non_silent_ranges = detect_silence(audio, min_silence_len=silence_chunk_len, silence_thresh=silence_threshold)
    if not non_silent_ranges:  # No silence detected
        return audio
    # Trim the audio to the range of non-silence
    start_trim = non_silent_ranges[0][0]
    end_trim = non_silent_ranges[-1][1]
    return audio[start_trim:end_trim]

def merge_audio_with_pauses(files_and_pauses, output_path):
    combined_audio = AudioSegment.empty()
    for file_path, pause_before, pause_after in files_and_pauses:
        audio = AudioSegment.from_mp3(file_path)
        trimmed_audio = trim_silence(audio)  # Trim silence at the start and end
        if pause_before:
            combined_audio += AudioSegment.silent(duration=pause_before)  # Add pause
        combined_audio += trimmed_audio
        if pause_after:
            combined_audio += AudioSegment.silent(duration=pause_after)  # Add pause
    combined_audio.export(output_path, format='mp3')

def get_mp3_duration(file_path):
    audio = AudioSegment.from_mp3(file_path)
    duration_seconds = len(audio) / 1000  # Convert milliseconds to seconds
    return duration_seconds
