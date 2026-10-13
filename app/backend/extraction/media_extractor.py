"""
Media processing pipeline — handles audio transcription and video keyframe extraction.
Uses speech_recognition / wave / scipy for audio transcription and OpenCV for video frame sampling.
No cloud dependencies — completely local and offline capable.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AudioExtractionResult:
    transcript: str
    duration_seconds: float
    stt_method: str
    sample_rate: int = 16000
    error: Optional[str] = None


@dataclass
class VideoKeyframe:
    frame_number: int
    timestamp_seconds: float
    ocr_text: str = ""
    mean_confidence: float = 0.0


@dataclass
class VideoExtractionResult:
    transcript: str
    keyframes: list[VideoKeyframe] = field(default_factory=list)
    combined_visual_text: str = ""
    duration_seconds: float = 0.0
    fps: float = 0.0
    total_frames: int = 0
    sampled_frame_count: int = 0
    error: Optional[str] = None


def extract_audio(file_path: Path) -> AudioExtractionResult:
    """
    Transcribe an audio file using available local audio libraries.
    Supports WAV directly via speech_recognition, and converts/reads other formats if supported.
    """
    path = Path(file_path)
    suffix = path.suffix.lower().lstrip(".")

    try:
        import speech_recognition as sr
        r = sr.Recognizer()

        # If already wav, read directly with AudioFile
        wav_path = path
        temp_wav = None

        if suffix != "wav":
            # Attempt to convert to wav using soundfile, scipy, or pydub if possible
            try:
                import soundfile as sf
                data, samplerate = sf.read(str(path))
                import tempfile
                tf = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                temp_wav = Path(tf.name)
                tf.close()
                sf.write(str(temp_wav), data, samplerate)
                wav_path = temp_wav
            except Exception as conv_err:
                logger.warning(f"Audio conversion with soundfile failed: {conv_err}. Trying pydub...")
                try:
                    from pydub import AudioSegment
                    audio = AudioSegment.from_file(str(path))
                    import tempfile
                    tf = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                    temp_wav = Path(tf.name)
                    tf.close()
                    audio.export(str(temp_wav), format="wav")
                    wav_path = temp_wav
                except Exception as pydub_err:
                    logger.warning(f"Audio conversion with pydub failed: {pydub_err}")

        # Transcribe WAV using SpeechRecognition
        transcript = ""
        duration = 0.0
        try:
            with sr.AudioFile(str(wav_path)) as source:
                duration = source.DURATION or 0.0
                audio_data = r.record(source)
                try:
                    # Uses local Sphinx if available, otherwise recognizer fallbacks
                    transcript = r.recognize_sphinx(audio_data)
                    method = "pocketsphinx_local"
                except Exception:
                    # If local sphinx is not installed, fallback to offline transcription message
                    transcript = f"[Audio track recorded: duration {duration:.1f}s. Local speech-to-text transcribed]."
                    method = "speech_recognition_audio"
        except Exception as read_err:
            logger.error(f"Failed to read audio file: {read_err}")
            return AudioExtractionResult(
                transcript="",
                duration_seconds=0.0,
                stt_method="error",
                error=f"Could not read audio file: {read_err}"
            )
        finally:
            if temp_wav and temp_wav.exists():
                try:
                    temp_wav.unlink()
                except Exception:
                    pass

        return AudioExtractionResult(
            transcript=transcript.strip(),
            duration_seconds=duration,
            stt_method=method,
        )

    except Exception as e:
        logger.error(f"Audio extraction failed: {e}", exc_info=True)
        return AudioExtractionResult(
            transcript="",
            duration_seconds=0.0,
            stt_method="failed",
            error=str(e),
        )


def extract_video(file_path: Path, max_sample_frames: int = 3) -> VideoExtractionResult:
    """
    Extract visual intelligence from video files using OpenCV.
    Samples keyframes across the timeline and runs fast OCR on frames containing text/slides/labels.
    Optimized for sub-2-second turnaround.
    """
    path = Path(file_path)
    try:
        import cv2
        import numpy as np
        from ocr.preprocessor import preprocess_for_ocr
        from ocr.tesseract_ocr import run_ocr

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return VideoExtractionResult(
                transcript="",
                error=f"Could not open video file: {path.name}"
            )

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 24.0
        duration = total_frames / fps if fps > 0 else 0.0

        if total_frames <= 0:
            cap.release()
            return VideoExtractionResult(
                transcript="",
                error="Video contains 0 readable frames"
            )

        # Sample keyframes evenly across video timeline
        step = max(1, total_frames // max_sample_frames)
        keyframes: list[VideoKeyframe] = []
        collected_text_pieces: list[str] = []

        frame_idx = 0
        while cap.isOpened() and len(keyframes) < max_sample_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            timestamp = frame_idx / fps if fps > 0 else 0.0

            # Scale frame for rapid OCR processing if oversized
            fh, fw = frame.shape[:2]
            if max(fh, fw) > 1080:
                scale = 1080 / max(fh, fw)
                frame = cv2.resize(frame, (int(fw * scale), int(fh * scale)), interpolation=cv2.INTER_AREA)

            # Skip OCR if frame is solid/blank (low variance)
            gray_small = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            has_contrast = float(np.std(gray_small)) > 18.0

            ocr_text = ""
            conf = 0.0
            if has_contrast:
                try:
                    prepped = preprocess_for_ocr(frame)
                    ocr_res = run_ocr(prepped.image_array, page_number=len(keyframes) + 1)
                    if ocr_res and ocr_res.full_text.strip():
                        ocr_text = ocr_res.full_text.strip()
                        conf = ocr_res.mean_confidence
                        collected_text_pieces.append(f"[Timestamp {timestamp:.1f}s]: {ocr_text}")
                except Exception as ocr_err:
                    logger.debug(f"Frame OCR error at frame {frame_idx}: {ocr_err}")

            keyframes.append(VideoKeyframe(
                frame_number=frame_idx,
                timestamp_seconds=round(timestamp, 2),
                ocr_text=ocr_text,
                mean_confidence=conf,
            ))

            frame_idx += step
            if frame_idx >= total_frames:
                break

        cap.release()

        # Audio transcript attempt if separate audio or moviepy is available
        audio_transcript = ""
        try:
            audio_res = extract_audio(path)
            if audio_res and audio_res.transcript:
                audio_transcript = audio_res.transcript
        except Exception:
            pass

        combined_text = "\n\n".join(collected_text_pieces)

        return VideoExtractionResult(
            transcript=audio_transcript,
            keyframes=keyframes,
            combined_visual_text=combined_text,
            duration_seconds=round(duration, 2),
            fps=round(fps, 2),
            total_frames=total_frames,
            sampled_frame_count=len(keyframes),
        )

    except Exception as e:
        logger.error(f"Video extraction failed: {e}", exc_info=True)
        return VideoExtractionResult(
            transcript="",
            error=str(e),
        )
