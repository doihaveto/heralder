function formatTime(timeInSeconds) {
    const minutes = Math.floor(timeInSeconds / 60);
    const seconds = Math.floor(timeInSeconds % 60);
    return `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
}

document.addEventListener('DOMContentLoaded', function() {
    const audio = document.getElementById('audio');
    const playPauseBtn = document.getElementById('play-pause-btn');
    const backBtn = document.getElementById('back-btn');
    const forwardBtn = document.getElementById('forward-btn');
    const muteBtn = document.getElementById('mute-btn');
    const speedDisplay = document.getElementById('speed-display');
    const currentTimeSpan = document.getElementById('current-time');
    const timeLeftSpan = document.getElementById('time-left');
    const progressBar = document.getElementById('progress-bar');
    const bufferedBar = document.getElementById('buffered-bar');
    const progressContainer = document.querySelector('.progress-container');

    const volumeSliderContainer = document.getElementById('volume-slider-container');
    const volumeSliderFill = document.getElementById('volume-slider-fill');
    const speedSliderContainer = document.getElementById('speed-slider-container');
    const speedSliderFill = document.getElementById('speed-slider-fill');
    const playerDiv = document.getElementById('audio-player');

    function updateTime() {
        const currentTime = audio.currentTime;
        const duration = audio.duration;
        const timeLeft = duration - currentTime;

        currentTimeSpan.textContent = formatTime(currentTime);
        timeLeftSpan.textContent = formatTime(timeLeft);

        // Update progress bar
        const progressPercent = (currentTime / duration) * 100;
        progressBar.style.width = `${progressPercent}%`;

        // Update buffered bar
        const buffered = audio.buffered;
        if (buffered.length) {
            const bufferedPercent = (buffered.end(buffered.length - 1) / duration) * 100;
            bufferedBar.style.width = `${bufferedPercent}%`;
        }
    }

    // Play / Pause Button
    playPauseBtn.addEventListener('click', () => {
        if (audio.paused) {
            audio.play();
            playPauseBtn.textContent = 'Pause';
        } else {
            audio.pause();
            playPauseBtn.textContent = 'Play';
        }
    });

    // Back Button (-10 seconds)
    backBtn.addEventListener('click', () => {
        audio.currentTime = Math.max(0, audio.currentTime - 10);
    });

    // Forward Button (+15 seconds)
    forwardBtn.addEventListener('click', () => {
        audio.currentTime = Math.min(audio.duration, audio.currentTime + 15);
    });

    // Mute Button
    muteBtn.addEventListener('click', () => {
        audio.muted = !audio.muted;
        muteBtn.textContent = audio.muted ? 'Unmute' : 'Mute';
    });

    // Update Time and Progress Bar
    audio.addEventListener('timeupdate', updateTime);

    // Initialize time display
    audio.addEventListener('loadedmetadata', () => {
        timeLeftSpan.textContent = formatTime(audio.duration);
    });

    // Play the audio when it's ready
    audio.addEventListener('canplay', () => {
        audio.play();
        playPauseBtn.textContent = 'Pause'; // Update button to show 'Pause'
    });

    // Seek through the audio by clicking on the progress bar
    progressContainer.addEventListener('click', (e) => {
        const rect = progressContainer.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const width = rect.width;
        const newTime = (clickX / width) * audio.duration;
        audio.currentTime = newTime;
    });

    // Custom Volume Control
    volumeSliderContainer.addEventListener('click', (e) => {
        const rect = volumeSliderContainer.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const volume = clickX / rect.width;
        audio.volume = volume;
        volumeSliderFill.style.width = `${volume * 100}%`;
    });

    // Custom Speed Control
    speedSliderContainer.addEventListener('click', (e) => {
        const rect = speedSliderContainer.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const speed = Math.round((0.5 + (clickX / rect.width) * 1.5) / 0.05) * 0.05; // Min 0.5x, Max 2x
        audio.playbackRate = speed;
        speedSliderFill.style.width = `${(speed - 0.5) / 1.5 * 100}%`;
        speedDisplay.textContent = `${speed.toFixed(2)}x`;
    });
});

function createAudioPlayer(audioUrl) {
    const playerDiv = document.getElementById('audio-player');
    const audio = document.getElementById('audio');
    const volumeSliderFill = document.getElementById('volume-slider-fill');
    const speedSliderFill = document.getElementById('speed-slider-fill');

    playerDiv.classList.remove('hidden');

    audio.src = audioUrl;

    // Initialize volume and speed
    audio.volume = 1;
    audio.playbackRate = 1;
    volumeSliderFill.style.width = '100%'; // Set initial volume fill to 100%
    speedSliderFill.style.width = '50%';  // Set initial speed fill to 50% (1x)
}

function formatNumberWithCommas(number) {
    // Convert the number to a string and use a regular expression for formatting
    return number.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}
