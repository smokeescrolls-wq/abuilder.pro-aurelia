#!/usr/bin/env python3
"""
AURELIA - STEALTH AUDIO CLOAKING SYSTEM
====================================================

Sistema dual-channel stealth para VSLs blackhat.
Humanos ouvem original limpo | IAs pegam white_loss.

Autor: Leonardo | Março 2026
"""

import os
import sys
import argparse
import tempfile
import shutil
import subprocess
import random
import warnings
import time
warnings.filterwarnings("ignore")

import numpy as np
import soundfile as sf
from scipy import signal
from scipy.ndimage import gaussian_filter1d

# ══════════════════════════════════════════════════════
# CORES HACKER STYLE
# ══════════════════════════════════════════════════════

class Colors:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"

def log(msg, level="info"):
    icons = {"info": "ℹ", "ok": "✓", "warn": "⚠", "err": "✗", "step": "→", "deploy": "[DEPLOY]"}
    colors = {"info": Colors.CYAN, "ok": Colors.GREEN, "warn": Colors.YELLOW, "err": Colors.RED, "step": Colors.CYAN, "deploy": Colors.GREEN}
    icon = icons.get(level, "•")
    color = colors.get(level, Colors.RESET)
    print(f"{color}{icon} {msg}{Colors.RESET}")

# ══════════════════════════════════════════════════════
# VERIFICAÇÕES
# ══════════════════════════════════════════════════════

def check_ffmpeg():
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except:
        return False

# ══════════════════════════════════════════════════════
# ÁUDIO I/O
# ══════════════════════════════════════════════════════

def load_audio(path, target_sr=44100):
    try:
        data, sr = sf.read(path, dtype='float32')
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        if sr != target_sr:
            num_samples = int(len(data) * target_sr / sr)
            data = signal.resample(data, num_samples)
        return data, target_sr
    except Exception as e:
        log(f"Erro ao carregar áudio: {e}", "err")
        return np.array([]), target_sr

def save_audio(path, data, sr=44100):
    try:
        data = np.clip(data, -1.0, 1.0)
        sf.write(path, data, sr, subtype='PCM_16')
        return True
    except Exception as e:
        log(f"Erro ao salvar áudio: {e}", "err")
        return False

# ══════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════

def rms(audio):
    return np.sqrt(np.mean(audio**2)) if len(audio) > 0 else 0.0

def normalize_to_rms(audio, target_rms=0.1):
    current = rms(audio)
    if current > 1e-6:
        return audio * (target_rms / current)
    return audio

def normalize_peak(audio, target_peak=0.95):
    peak = np.max(np.abs(audio))
    if peak > 1e-6:
        return audio * (target_peak / peak)
    return audio

def apply_bandpass(audio, sr, lowcut, highcut, order=6):
    nyq = sr / 2
    low = np.clip(lowcut / nyq, 0.001, 0.999)
    high = np.clip(highcut / nyq, 0.001, 0.999)
    if high <= low:
        return audio
    try:
        sos = signal.butter(order, [low, high], btype='band', output='sos')
        return signal.sosfilt(sos, audio).astype(np.float32)
    except:
        return audio

# ══════════════════════════════════════════════════════
# FIX DE DURAÇÃO (v16)
# ══════════════════════════════════════════════════════

def pad_or_repeat_audio(audio, target_samples):
    if len(audio) >= target_samples:
        return audio[:target_samples]
    repeats = (target_samples // len(audio)) + 2
    repeated = np.tile(audio, repeats)
    return repeated[:target_samples].astype(np.float32)

# ══════════════════════════════════════════════════════
# DUAL STREAM CORE
# ══════════════════════════════════════════════════════

def build_dual_stream_video(video_path, original_wav, white_wav, output_path,
                             bitrate_original="192k", bitrate_white="128k"):
    log("Deploying dual-stream cloaking...", "deploy")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", white_wav,
        "-i", original_wav,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-map", "2:a:0",
        "-c:v", "copy",
        "-c:a:0", "aac", "-b:a:0", bitrate_white, "-ac:0", "1",
        "-c:a:1", "aac", "-b:a:1", bitrate_original,
        "-metadata:s:a:0", "title=Audio",
        "-metadata:s:a:0", "language=und",
        "-metadata:s:a:1", "title=Audio Principal",
        "-metadata:s:a:1", "language=por",
        "-disposition:a:0", "default",
        "-disposition:a:1", "0",
        "-shortest",
        "-movflags", "+faststart",
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(output_path):
            log("Cloaking dual-stream ativado com sucesso", "ok")
            return True
        else:
            log(f"FFmpeg error: {result.stderr[-300:]}", "err")
            return False
    except Exception as e:
        log(f"Erro no deploy: {e}", "err")
        return False

def build_dual_stream_video_v2(video_path, original_wav, white_wav, output_path,
                                bitrate_original="192k", bitrate_white="128k"):
    log("Tentando deploy alternativo (MKV → MP4)...", "step")
    tmp_dir = os.path.dirname(output_path)
    tmp_mkv = os.path.join(tmp_dir, "_temp_dual.mkv")
    
    cmd_mkv = [
        "ffmpeg", "-y", "-i", video_path, "-i", white_wav, "-i", original_wav,
        "-map", "0:v:0", "-map", "1:a:0", "-map", "2:a:0",
        "-c:v", "copy", "-c:a:0", "aac", "-b:a:0", bitrate_white,
        "-c:a:1", "aac", "-b:a:1", bitrate_original,
        "-metadata:s:a:0", "title=Audio",
        "-metadata:s:a:1", "title=Audio Principal",
        "-disposition:a:0", "default", "-disposition:a:1", "0",
        "-shortest", tmp_mkv
    ]
    
    try:
        result = subprocess.run(cmd_mkv, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            if os.path.exists(tmp_mkv): os.remove(tmp_mkv)
            return False
        cmd_mp4 = ["ffmpeg", "-y", "-i", tmp_mkv, "-c", "copy", "-movflags", "+faststart", output_path]
        result2 = subprocess.run(cmd_mp4, capture_output=True, text=True, timeout=300)
        if os.path.exists(tmp_mkv): os.remove(tmp_mkv)
        return result2.returncode == 0 and os.path.exists(output_path)
    except:
        if os.path.exists(tmp_mkv): os.remove(tmp_mkv)
        return False

# ══════════════════════════════════════════════════════
# SPECTRAL MIX (BACKUP)
# ══════════════════════════════════════════════════════

def spectral_mix_light(original, white_loss, sr, ratio=0.5):
    mn = min(len(original), len(white_loss))
    o = original[:mn].copy()
    w = white_loss[:mn].copy()
    w = normalize_to_rms(w, rms(o))
    w_core = apply_bandpass(w, sr, 200, 3500, order=4)
    white_vol = (1.0 - ratio) * 0.3
    mixed = o + (w_core * white_vol)
    mixed = normalize_peak(mixed, target_peak=0.95)
    return mixed

# ══════════════════════════════════════════════════════
# TTS - WHITE LOSS
# ══════════════════════════════════════════════════════

WHITE_SCRIPTS = {
    "mmo": (
        "Building a sustainable online business starts with understanding your audience "
        "and providing genuine value. Digital marketing strategies evolve constantly, "
        "so staying informed about current trends is essential. Content creation, email "
        "marketing, and search engine optimization are foundational skills for anyone "
        "looking to grow an online presence. Diversifying income streams helps create "
        "financial stability over time. Learning from established entrepreneurs and "
        "investing in education can accelerate your journey. Consistency and patience "
        "are key virtues in the digital economy. Building trust with your audience "
        "through transparency leads to long-term success and customer loyalty."
    ),
    "wealth": (
        "Financial literacy is one of the most important skills for long-term prosperity. "
        "Understanding compound interest, asset allocation, and risk management forms "
        "the foundation of sound financial planning. Creating a budget and tracking "
        "expenses helps identify opportunities for savings and investment. Diversifying "
        "your portfolio across different asset classes reduces overall risk. Consulting "
        "with a qualified financial advisor can provide personalized guidance based on "
        "your specific goals and circumstances. Building an emergency fund provides a "
        "safety net for unexpected situations. Starting early and being consistent with "
        "contributions maximizes the power of compound growth over decades."
    ),
    "weight_loss": (
        "Maintaining a healthy weight involves a combination of balanced nutrition "
        "and regular physical activity. Experts recommend focusing on whole foods, "
        "lean proteins, and plenty of vegetables. Regular exercise, even just thirty "
        "minutes a day of walking, can make a significant difference. Remember to stay "
        "hydrated and get adequate sleep for optimal metabolic health. Consulting with "
        "a healthcare professional is always recommended before starting any new health "
        "routine. Small changes in daily habits can lead to significant improvements "
        "over time. A balanced approach to weight management includes both dietary "
        "adjustments and increased physical activity for sustainable results."
    ),
    "diabetes": (
        "Managing blood sugar levels is a cornerstone of metabolic health. A balanced "
        "diet rich in fiber, whole grains, and lean proteins helps maintain steady "
        "glucose levels throughout the day. Regular physical activity improves insulin "
        "sensitivity and supports cardiovascular health. Monitoring your health metrics "
        "and maintaining regular consultations with healthcare providers ensures proactive "
        "management. Stress management techniques such as meditation and adequate sleep "
        "also play important roles in metabolic regulation. Staying informed about "
        "nutritional science and evidence-based approaches empowers better daily choices. "
        "Community support and education are valuable resources for anyone focused on "
        "improving their metabolic wellness journey."
    ),
    "ed": (
        "Men's health encompasses many aspects of physical and mental wellbeing. "
        "Regular check ups with your healthcare provider can help identify concerns "
        "early. A balanced diet rich in fruits, vegetables, and whole grains supports "
        "overall vitality. Exercise and stress management play crucial roles in "
        "maintaining good health. Sleep quality and duration significantly impact "
        "hormonal balance and overall wellness. Staying active and maintaining social "
        "connections contribute to long term health outcomes. Prevention through "
        "regular screening is key to addressing health concerns proactively."
    ),
    "brain": (
        "Cognitive health is influenced by a combination of lifestyle factors that "
        "support brain function throughout life. Regular mental stimulation through "
        "reading, puzzles, and learning new skills helps maintain neural pathways. "
        "Physical exercise increases blood flow to the brain and promotes the growth "
        "of new neural connections. A Mediterranean-style diet rich in omega-three "
        "fatty acids, antioxidants, and whole grains supports cognitive function. "
        "Quality sleep is essential for memory consolidation and mental clarity. "
        "Social engagement and meaningful relationships contribute to emotional "
        "resilience and cognitive reserve. Managing stress through mindfulness and "
        "relaxation techniques protects long-term brain health."
    ),
    "anti_aging": (
        "Healthy aging is a holistic process that involves caring for both body and "
        "mind. Antioxidant-rich foods such as berries, leafy greens, and nuts help "
        "combat oxidative stress at the cellular level. Regular physical activity "
        "maintains muscle mass, bone density, and cardiovascular health as we age. "
        "Adequate hydration and sun protection are simple yet effective daily habits. "
        "Quality sleep supports cellular repair and regeneration processes. Staying "
        "socially active and mentally engaged contributes to overall vitality and "
        "life satisfaction. Consulting with healthcare professionals about preventive "
        "care and age-appropriate screenings helps maintain optimal wellness."
    ),
    "joint_pain": (
        "Joint health and mobility are fundamental to maintaining an active lifestyle. "
        "Low-impact exercises such as swimming, cycling, and yoga help strengthen "
        "supporting muscles without excessive strain on joints. Maintaining a healthy "
        "weight reduces mechanical stress on weight-bearing joints significantly. "
        "Anti-inflammatory foods including fatty fish, turmeric, and leafy greens "
        "support joint comfort naturally. Proper posture and ergonomic awareness during "
        "daily activities help prevent unnecessary strain. Stretching and flexibility "
        "exercises improve range of motion and reduce stiffness. Consulting with a "
        "physical therapist can provide personalized exercise programs tailored to "
        "your specific needs and goals."
    ),
    "vision": (
        "Eye health depends on a combination of proper nutrition, regular check-ups, "
        "and daily protective habits. Foods rich in vitamins A, C, and E along with "
        "zinc and omega-three fatty acids support optimal visual function. Protecting "
        "your eyes from excessive blue light exposure and ultraviolet radiation helps "
        "preserve long-term eye health. Regular comprehensive eye exams can detect "
        "changes early when they are most manageable. Taking breaks from screen time "
        "using the twenty-twenty-twenty rule reduces digital eye strain effectively. "
        "Adequate hydration supports tear production and overall eye comfort. "
        "Maintaining good lighting when reading or working reduces unnecessary strain."
    ),
    "hair_loss": (
        "Hair health is influenced by nutrition, genetics, and overall wellness habits. "
        "A balanced diet rich in biotin, iron, zinc, and protein provides the building "
        "blocks for healthy hair growth. Gentle hair care practices including avoiding "
        "excessive heat styling and harsh chemical treatments help maintain hair integrity. "
        "Scalp health plays a crucial role in supporting hair follicle function. Regular "
        "massage and proper cleansing promote circulation and a healthy scalp environment. "
        "Managing stress through relaxation techniques and adequate sleep supports the "
        "natural hair growth cycle. Consulting with a dermatologist can provide personalized "
        "guidance based on individual factors and the latest evidence-based approaches."
    ),
    "general": (
        "Health and wellness are important aspects of everyday life. Making informed "
        "decisions about your lifestyle can lead to positive outcomes. Regular physical "
        "activity, balanced nutrition, and adequate rest form the pillars of good health. "
        "Staying connected with friends and family supports mental and emotional wellbeing. "
        "Taking time for self care and relaxation helps manage daily stress effectively."
    ),
}

def tts_pyttsx3(text, out_wav, sr=44100):
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        for v in voices:
            nm = v.name.lower()
            if any(k in nm for k in ['english', 'en-us', 'en_us', 'zira', 'david', 'mark']):
                engine.setProperty('voice', v.id)
                break
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 1.0)
        tmp = out_wav + ".tmp.wav"
        engine.save_to_file(text, tmp)
        engine.runAndWait()
        engine.stop()
        if os.path.exists(tmp) and os.path.getsize(tmp) > 500:
            subprocess.run(["ffmpeg", "-y", "-i", tmp, "-ar", str(sr), "-ac", "1", "-acodec", "pcm_s16le", out_wav], capture_output=True, check=True)
            os.remove(tmp)
            return True
    except Exception as e:
        log(f"pyttsx3 falhou: {e}", "warn")
    return False

def tts_edge(text, out_wav, sr=44100):
    try:
        import asyncio
        import edge_tts
        async def _generate():
            communicate = edge_tts.Communicate(text, "en-US-GuyNeural")
            tmp = out_wav + ".tmp.mp3"
            await communicate.save(tmp)
            subprocess.run(["ffmpeg", "-y", "-i", tmp, "-ar", str(sr), "-ac", "1", "-acodec", "pcm_s16le", out_wav], capture_output=True, check=True)
            if os.path.exists(tmp): os.remove(tmp)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.wait_for(_generate(), timeout=15))
        return os.path.exists(out_wav) and os.path.getsize(out_wav) > 500
    except Exception as e:
        log(f"edge-tts falhou: {e}", "warn")
    return False

def tts_gtts(text, out_wav, sr=44100):
    try:
        from gtts import gTTS
        tmp = out_wav + ".tmp.mp3"
        tts = gTTS(text=text, lang='en')
        tts.save(tmp)
        subprocess.run(["ffmpeg", "-y", "-i", tmp, "-ar", str(sr), "-ac", "1", "-acodec", "pcm_s16le", out_wav], capture_output=True, check=True)
        if os.path.exists(tmp): os.remove(tmp)
        return os.path.exists(out_wav) and os.path.getsize(out_wav) > 500
    except Exception as e:
        log(f"gTTS falhou: {e}", "warn")
    return False

def prepare_white_loss(white_path, category, target_len, sr, tmp_dir):
    if category == "random":
        category = random.choice(list(WHITE_SCRIPTS.keys()))
        log(f"Categoria aleatória: {category}", "info")
    
    if white_path and os.path.exists(white_path):
        log(f"Usando áudio customizado: {white_path}", "info")
        w, _ = load_audio(white_path, target_sr=sr)
        if len(w) > 0:
            return w[:target_len], category
    
    tts_out = os.path.join(tmp_dir, "white_tts.wav")
    script = WHITE_SCRIPTS.get(category, WHITE_SCRIPTS["general"])
    
    log("Gerando TTS com pyttsx3 (offline)...", "step")
    if tts_pyttsx3(script, tts_out, sr=sr):
        log("TTS gerado com pyttsx3!", "ok")
    else:
        log("Tentando edge-tts (online)...", "step")
        if tts_edge(script, tts_out, sr=sr):
            log("TTS gerado com edge-tts!", "ok")
        else:
            log("Tentando gTTS (online)...", "step")
            if tts_gtts(script, tts_out, sr=sr):
                log("TTS gerado com gTTS!", "ok")
            else:
                log("Nenhum TTS disponível! Gerando ruído de fala...", "warn")
                noise = np.random.randn(target_len).astype(np.float32) * 0.1
                noise = apply_bandpass(noise, sr, 300, 3500, order=4)
                return noise, category
    
    w, _ = load_audio(tts_out, target_sr=sr)
    if len(w) > 0:
        return w[:target_len], category
    
    noise = np.random.randn(target_len).astype(np.float32) * 0.1
    return noise, category

# ══════════════════════════════════════════════════════
# PROCESSAMENTO DE VÍDEO
# ══════════════════════════════════════════════════════

def extract_audio_from_video(video_path, output_wav, sr=44100):
    try:
        cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-ar", str(sr), "-ac", "1", "-acodec", "pcm_s16le", output_wav]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return os.path.exists(output_wav)
    except subprocess.CalledProcessError as e:
        log(f"Erro ao extrair áudio: {e.stderr}", "err")
        return False

def get_video_duration(video_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except:
        return 0.0

def merge_single_stream(video_path, audio_path, output_path, bitrate="192k"):
    try:
        cmd = ["ffmpeg", "-y", "-i", video_path, "-i", audio_path, "-c:v", "copy", "-c:a", "aac", "-b:a", bitrate, "-map", "0:v:0", "-map", "1:a:0", "-shortest", "-movflags", "+faststart", output_path]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return os.path.exists(output_path)
    except subprocess.CalledProcessError as e:
        log(f"Erro ao mesclar: {e.stderr}", "err")
        return False

def verify_streams(video_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index,codec_name,bit_rate,channels", "-of", "csv=p=0", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        return lines
    except:
        return []

# ══════════════════════════════════════════════════════
# MAIN - INTERFACE HACKER
# ══════════════════════════════════════════════════════

def main():
    banner = f"""
{Colors.GREEN}
[ A U R E L I A ]  STEALTH AUDIO CLOAKING SYSTEM
[STATUS] SYSTEM ONLINE - DUAL-CHANNEL DEPLOYED
[MODE]   WHITE_LOSS → IA | ORIGINAL → HUMAN
{Colors.RESET}
"""
    print(banner)
    
    parser = argparse.ArgumentParser(description="AURELIA - Stealth Audio Cloaking")
    parser.add_argument("video", help="Caminho do vídeo (.mp4)")
    parser.add_argument("--output", "-o", help="Saída (padrão: video_shielded.mp4)")
    parser.add_argument("--category", "-c", default="ed")
    parser.add_argument("--white-audio", help="White loss customizado")
    parser.add_argument("--strategy", "-s", default="dual", choices=["dual", "hybrid", "spectral"])
    parser.add_argument("--ratio", "-r", type=float, default=0.6)
    parser.add_argument("--audio-bitrate", default="192k")
    parser.add_argument("--white-bitrate", default="128k")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--export-layers", action="store_true")
    
    args = parser.parse_args()
    args.video = os.path.abspath(args.video)
    
    if not os.path.exists(args.video):
        log("Vídeo não encontrado no sistema", "err")
        return 1
    if not check_ffmpeg():
        log("FFmpeg não detectado. Instale antes de continuar.", "err")
        return 1
    
    if args.output:
        output_video = os.path.abspath(args.output)
    else:
        base, ext = os.path.splitext(args.video)
        output_video = f"{base}_shielded{ext}"
    
    sr = args.sample_rate
    tmp_dir = tempfile.mkdtemp(prefix="aurelia_")
    
    try:
        log("Iniciando protocolo de cloaking...", "step")
        log(f"Alvo: {args.video}", "info")
        log(f"Saída: {output_video}", "info")
        
        duration = get_video_duration(args.video)
        log(f"Duração detectada: {duration:.2f}s", "info")
        
        # Extrai original
        original_wav = os.path.join(tmp_dir, "original.wav")
        extract_audio_from_video(args.video, original_wav, sr)
        original, _ = load_audio(original_wav, sr)
        
        # White loss
        white_loss, category = prepare_white_loss(args.white_audio, args.category, len(original), sr, tmp_dir)
        white_loss = normalize_to_rms(white_loss, rms(original))
        
        # FIX duração
        white_loss = pad_or_repeat_audio(white_loss, len(original))
        log(f"White_loss sincronizado com duração exata", "ok")
        
        # Deploy
        success = False
        if args.strategy == "dual":
            log("Deploying dual-channel stealth...", "deploy")
            original_out = os.path.join(tmp_dir, "stream_original.wav")
            white_out = os.path.join(tmp_dir, "stream_white.wav")
            save_audio(original_out, original, sr)
            save_audio(white_out, white_loss, sr)
            
            success = build_dual_stream_video(args.video, original_out, white_out, output_video,
                                              args.audio_bitrate, args.white_bitrate)
            if not success:
                success = build_dual_stream_video_v2(args.video, original_out, white_out, output_video,
                                                     args.audio_bitrate, args.white_bitrate)
        
        elif args.strategy == "hybrid":
            log("Deploying hybrid cloaking (dual + spectral backup)...", "deploy")
            white_out = os.path.join(tmp_dir, "stream_white.wav")
            mixed = spectral_mix_light(original, white_loss, sr, args.ratio)
            mixed_out = os.path.join(tmp_dir, "stream_mixed.wav")
            save_audio(white_out, white_loss, sr)
            save_audio(mixed_out, mixed, sr)
            success = build_dual_stream_video(args.video, mixed_out, white_out, output_video,
                                              args.audio_bitrate, args.white_bitrate)
        
        elif args.strategy == "spectral":
            log("Deploying spectral mix (legacy mode)...", "deploy")
            mixed = spectral_mix_light(original, white_loss, sr, args.ratio)
            mixed_out = os.path.join(tmp_dir, "mixed.wav")
            save_audio(mixed_out, mixed, sr)
            success = merge_single_stream(args.video, mixed_out, output_video, args.audio_bitrate)
        
        if success and os.path.exists(output_video):
            size_mb = os.path.getsize(output_video) / (1024 * 1024)
            streams = verify_streams(output_video)
            
            log("═" * 50, "info")
            log(f"[SUCCESS] Cloaking finalizado → {output_video}", "ok")
            log(f"Tamanho: {size_mb:.1f} MB | Streams: {len(streams)}", "info")
            
            print(f"\n{Colors.GREEN}[ AURELIA DEPLOYED SUCCESSFULLY ]{Colors.RESET}")
            print(f"   Humanos → áudio original limpo (auto)")
            print(f"   IAs (AssemblyAI, Meta, etc.) → white_loss detectado")
            print(f"\n{Colors.CYAN}Sistema pronto. Suba o arquivo e teste.{Colors.RESET}")
            
            return 0
        else:
            log("Falha no deploy do cloaking", "err")
            return 1
            
    except Exception as e:
        log(f"Erro inesperado: {e}", "err")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    sys.exit(main())