#!/usr/bin/env python3
"""
basay_clone.py — 巴賽語(Basay)的文字，用VoxCPM2複製的你的聲音正確地唸出來。

三段式流程：
  1. basay_text.py 將巴賽語表記轉換成 espeak 音素文字（[[...]] 記法）
  2. 透過 basay.tw 正式服務（https://inkuei-basaytts.hf.space/ 的 /synth_wav
     API，跟辭典頁面 https://basay.tw/dictionary/ 用的是同一套合成引擎）把
     音素文字合成為機械人聲。預設用 tai/bsystd（台語適配・Lobanov 正規化），
     因為音韻與 seed-vc 訓練語言較接近，聲音轉換後內容較不易跑掉；
     tai/bsy（Ipay 歷史復原・基於 Asai 1936 Mutravai 方言的聲學重建）音韻
     更精確，但 seed-vc 較容易誤判。
     （也可以用 --espeak-backend local 改用本機編譯的 espeak-ng，見下方）
  3. 用 seed-vc 把這段機械人聲轉換成 voices/<voice>/ref_voice.wav 的複製聲音
     （只換音色，內容與語調保留）

這跟 VoxCPM2 本身的 clone.py（中文・英文用，直接把文字交給模型朗讀）是不同的
管線。因為VoxCPM2沒學過巴賽語，所以用espeak端的音素合成來保證發音正確。

用法:
  python basay_clone.py "Makawas ita mau Basay" --voice <你的複製聲音名稱>
  python basay_clone.py "ita" --voice <聲音名稱> --espeak-voice tai/bsy
  python basay_clone.py --file basay_script.txt --voice <聲音名稱>

前提（完整安裝步驟見 SETUP.md）:
  - 本repo放在 voxcpm2-voice-cloner 專案目錄下的子資料夾（例如取名 basay/），
    這樣才能讀到上層的 voices/<voice>/ref_voice.wav
  - basay/seed-vc/.venv-seedvc 已安裝好 seed-vc 的相依套件
    （--espeak-backend remote＝預設值時，不需要本機編譯espeak-ng）
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

BASAY_DIR = Path(__file__).resolve().parent
REPO_DIR = BASAY_DIR.parent
sys.path.insert(0, str(BASAY_DIR))
import basay_text  # noqa: E402

ESPEAK_BUILD_DIR = BASAY_DIR / "espeak-build"
ESPEAK_BIN = ESPEAK_BUILD_DIR / "src" / ("espeak-ng.exe" if os.name == "nt" else "espeak-ng")
SEEDVC_DIR = BASAY_DIR / "seed-vc"
# venv内のpython配置はOSで異なる: Unix系は bin/python、Windowsは Scripts/python.exe
SEEDVC_PY = (
    SEEDVC_DIR / ".venv-seedvc" / "Scripts" / "python.exe" if os.name == "nt"
    else SEEDVC_DIR / ".venv-seedvc" / "bin" / "python"
)

# basay.tw本番Space。ローカルでespeak-ngをビルドする代わりに、辞書更新でも
# 使われている本番の合成エンジンをそのまま使う場合のバックエンド。
REMOTE_SPACE_URL = "https://inkuei-basaytts.hf.space/"
_remote_client = None

_EMBEDDED_PHONEMES_RE = re.compile(r'(\[\[.*?\]\])')


def normalize_embedded_phonemes(text):
    """[[ ]] フレーズ記法ブロック内の y/Y を j に統一する
    （bsy_rules の .group y: y -> j に合わせるための後処理。
     basaytts-space の app.py の normalize_embedded_phonemes と同じロジック）。"""
    def repl(m):
        inner = m.group(0)[2:-2]
        return '[[' + inner.replace('y', 'j').replace('Y', 'j') + ']]'
    return _EMBEDDED_PHONEMES_RE.sub(repl, text)


def basay_to_phoneme_text(display_text):
    raw = basay_text.tts_text(display_text)
    return normalize_embedded_phonemes(raw)


def synth_espeak(phoneme_text, espeak_voice, out_wav, speed=None):
    if not ESPEAK_BIN.exists():
        sys.exit(
            f"エラー: espeak-ngが見つかりません: {ESPEAK_BIN}\n"
            f"先に basay/SETUP.md の手順でビルドしてください。"
        )
    env = os.environ.copy()
    env["ESPEAK_DATA_PATH"] = str(ESPEAK_BUILD_DIR)
    cmd = [str(ESPEAK_BIN), "-v", espeak_voice, "-a", "200"]
    if speed:
        # espeak-ng既定は約175 wpm。下げると子音がはっきりして
        # seed-vc側での子音の欠落/弱化を軽減できる場合がある。
        cmd += ["-s", str(speed)]
    cmd += ["-w", str(out_wav), phoneme_text]
    subprocess.run(cmd, env=env, check=True)


def synth_espeak_remote(phoneme_text, espeak_voice, out_wav):
    """ローカルのespeak-ngビルドの代わりに、basay.tw本番Space
    (basay.tw/dictionary/ の音声生成で実際に使われているのと同じバックエンド)の
    /synth_wav APIを呼んで合成する。tts_text（音素テキスト）とvoice_short
    （'bsy'/'bsystd'、tai/プレフィックスなし）を渡し、生成済みwavのパスを受け取る。"""
    global _remote_client
    try:
        from gradio_client import Client
    except ImportError:
        sys.exit(
            "エラー: gradio_clientが必要です。\n"
            "  pip install gradio_client"
        )
    if _remote_client is None:
        print(f"  (リモートSpaceに接続中: {REMOTE_SPACE_URL})")
        _remote_client = Client(REMOTE_SPACE_URL)

    voice_short = espeak_voice.rsplit("/", 1)[-1]  # "tai/bsystd" -> "bsystd"
    result_path = _remote_client.predict(
        phoneme_text, voice_short, api_name="/synth_wav"
    )
    shutil.copyfile(result_path, out_wav)


def do_synth_espeak(phoneme_text, args, out_wav):
    """args.espeak_backendに応じてローカル/リモートのespeak合成を振り分ける。"""
    if args.espeak_backend == "remote":
        synth_espeak_remote(phoneme_text, args.espeak_voice, out_wav)
    else:
        synth_espeak(phoneme_text, args.espeak_voice, out_wav, speed=args.espeak_speed)


# basaytts-space(gen_audio.py等)と揃えた既定のラウドネス正規化フィルタ。
LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true"


def normalize_audio(wav_path):
    """seed-vc変換後の最終出力をffmpeg loudnormで正規化する（espeak側・既存の
    gen_audio.py/Spaceと同じ基準に揃える）。ffmpegが無ければ無音でスキップ。"""
    if shutil.which("ffmpeg") is None:
        print("  警告: ffmpegが見つからないため正規化をスキップしました。")
        return
    tmp = wav_path.with_suffix(".norm.wav")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path), "-af", LOUDNORM_FILTER, str(tmp)]
    try:
        subprocess.run(cmd, check=True)
        tmp.replace(wav_path)
    except subprocess.CalledProcessError as e:
        print(f"  警告: 正規化に失敗しました: {e}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def convert_voice(source_wav, target_wav, output_dir, diffusion_steps=30,
                   vc_version="v1", intelligibility_cfg_rate=0.7, similarity_cfg_rate=0.7,
                   fp16=False):
    if not SEEDVC_PY.exists():
        sys.exit(
            f"エラー: seed-vc用venvが見つかりません: {SEEDVC_PY}\n"
            f"先に basay/SETUP.md の手順で .venv-seedvc を作成してください。"
        )
    if vc_version == "v2":
        # V2: AR+CFM構成。intelligibility-cfg-rateを上げると発音の明瞭さ（内容忠実性）を
        # 優先し、similarity-cfg-rateを上げると音色の類似度を優先する。
        cmd = [
            str(SEEDVC_PY), "inference_v2.py",
            "--source", str(source_wav),
            "--target", str(target_wav),
            "--output", str(output_dir),
            "--diffusion-steps", str(diffusion_steps),
            "--length-adjust", "1.0",
            "--intelligibility-cfg-rate", str(intelligibility_cfg_rate),
            "--similarity-cfg-rate", str(similarity_cfg_rate),
            "--convert-style", "False",
            "--anonymization-only", "False",
        ]
    else:
        cmd = [
            str(SEEDVC_PY), "inference.py",
            "--source", str(source_wav),
            "--target", str(target_wav),
            "--output", str(output_dir),
            "--diffusion-steps", str(diffusion_steps),
            "--length-adjust", "1.0",
            "--inference-cfg-rate", "0.7",
            "--f0-condition", "False",
            "--fp16", "True" if fp16 else "False",
        ]
    subprocess.run(cmd, cwd=str(SEEDVC_DIR), check=True)


def concatenate_wavs(wav_paths, output_path, gap_seconds=0.15):
    """複数のWAV（同一フォーマット前提）を、無音を挟んで連結する。
    単語ごとに変換した結果を1本につなげるために使う。"""
    if len(wav_paths) == 1:
        shutil.copyfile(wav_paths[0], output_path)
        return
    params = None
    gap_frames = None
    frames_list = []
    for p in wav_paths:
        with wave.open(str(p), "rb") as src:
            if params is None:
                params = src.getparams()
                silence = bytes(params.sampwidth * params.nchannels)
                gap_frames = silence * int(params.framerate * gap_seconds)
            elif src.getparams()[:3] != params[:3]:
                raise RuntimeError(
                    f"WAVフォーマットが一致しません（{p}）。連結できません。"
                )
            frames_list.append(src.readframes(src.getnframes()))
    with wave.open(str(output_path), "wb") as dst:
        dst.setparams(params)
        for i, frames in enumerate(frames_list):
            if i and gap_frames:
                dst.writeframes(gap_frames)
            dst.writeframes(frames)


def process_one_utterance(text, args, tmpdir, label=""):
    """1つの発話（単語 or 全文）を espeak合成 -> seed-vc変換まで処理し、
    変換後wavのPathを返す。"""
    phoneme_text = basay_to_phoneme_text(text)
    print(f"  [{label}] 表記: {text!r}  音素: {phoneme_text!r}")

    espeak_wav = tmpdir / f"espeak_{label}.wav"
    do_synth_espeak(phoneme_text, args, espeak_wav)

    vc_out_dir = tmpdir / f"vc_out_{label}"
    vc_out_dir.mkdir()
    convert_voice(
        espeak_wav, REPO_DIR / "voices" / args.voice / "ref_voice.wav", vc_out_dir,
        args.diffusion_steps,
        vc_version=args.vc_version,
        intelligibility_cfg_rate=args.intelligibility_cfg_rate,
        similarity_cfg_rate=args.similarity_cfg_rate,
        fp16=args.fp16,
    )
    produced = sorted(vc_out_dir.glob("*.wav"))
    if not produced:
        sys.exit(f"エラー: seed-vcが音声を生成しませんでした（{label}）。")
    return produced[0], espeak_wav


def main():
    ap = argparse.ArgumentParser(description="巴賽語テキストをクローン声で発音させる")
    ap.add_argument("text", nargs="?", help="巴賽語表記（クォートで囲む）")
    ap.add_argument("--file", "-f", help="巴賽語表記を含むテキストファイル")
    ap.add_argument("--voice", "-v", required=True,
                     help="VoxCPM2 voices/<名前> に対応するクローン声の名前")
    ap.add_argument("--espeak-voice", default="tai/bsystd",
                     help="espeak-ngボイス: tai/bsystd（台語適合・既定。seed-vc変換時の"
                          "内容保持が良い）または tai/bsy（Ipay歴史復元。音韻はより正確だが"
                          "seed-vc側で誤認識されやすい）")
    ap.add_argument("--espeak-backend", choices=["remote", "local"], default="remote",
                     help="espeak合成の実行先。remote（既定）はbasay.tw本番Space"
                          f"（{REMOTE_SPACE_URL}、辞書更新と同じ合成エンジン）をgradio_client"
                          "経由で呼ぶ。local は basay/espeak-build のローカルビルドを使う"
                          "（要 SETUP.md の手順、--espeak-speedはlocal限定）")
    ap.add_argument("--diffusion-steps", type=int, default=30,
                     help="seed-vc拡散ステップ数（既定30、速さ優先なら10〜15に下げる）")
    ap.add_argument("--espeak-speed", type=int, default=None,
                     help="(--espeak-backend local のみ) espeak-ngの発話速度(wpm、既定175)。"
                          "下げると子音がはっきりし、seed-vc変換後の子音欠落が軽減される"
                          "場合がある（例: 140）")
    ap.add_argument("--vc-version", choices=["v1", "v2"], default="v1",
                     help="seed-vcのモデル版。v2は--intelligibility-cfg-rateで発音明瞭さを"
                          "直接優先できるため、子音欠落が気になる場合はv2を試す")
    ap.add_argument("--intelligibility-cfg-rate", type=float, default=0.7,
                     help="(v2のみ) 発音の明瞭さ/内容忠実性の重み。上げる(例:0.9)と"
                          "子音欠落が減りやすいが音色類似度が下がる場合がある")
    ap.add_argument("--similarity-cfg-rate", type=float, default=0.7,
                     help="(v2のみ) 音色類似度の重み")
    ap.add_argument("--fp16", action="store_true",
                     help="(v1のみ) fp16推論を使う。既定はfp32（MacのMPSではfp16が"
                          "音質劣化/濁りの原因になることがあるため）")
    ap.add_argument("--no-normalize", action="store_true",
                     help="最終出力のラウドネス正規化(ffmpeg loudnorm)をスキップする。"
                          "既定では basaytts-space/gen_audio.py と同じ基準で正規化する")
    ap.add_argument("--per-word", action="store_true",
                     help="複数語を1文として一括変換せず、単語ごとにespeak合成+seed-vc変換し"
                          "最後に無音を挟んで結合する。語頭/語尾の子音の欠落・変質が"
                          "気になる場合に有効（変換回数が増えるため処理時間も増える）")
    ap.add_argument("--word-gap", type=float, default=0.15,
                     help="(--per-word時) 単語間に挟む無音の長さ(秒、既定0.15)")
    ap.add_argument("--output", "-o", default="output/basay_cloned.wav")
    ap.add_argument("--keep-espeak-wav", action="store_true",
                     help="espeakが合成した中間ファイル（変換前のロボット声）も残す")
    args = ap.parse_args()

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8").strip()
    elif args.text:
        text = args.text
    else:
        sys.exit("エラー: 巴賽語テキストを指定してください（または --file）。")

    ref_wav = REPO_DIR / "voices" / args.voice / "ref_voice.wav"
    if not ref_wav.exists():
        sys.exit(
            f"エラー: 参考音声が見つかりません: {ref_wav}\n"
            f"先に record.py --voice {args.voice} （または app.py の録音UI）で録音してください。"
        )

    print(f"表記: {text}")
    print(f"espeakボイス: {args.espeak_voice}")
    print(f"クローン声: {args.voice} ({ref_wav})")
    print(f"モード: {'単語ごと' if args.per_word else '全文一括'}  vc-version: {args.vc_version}")

    out_path = (REPO_DIR / args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="basay_clone_") as tmpdir:
        tmpdir = Path(tmpdir)

        if args.per_word:
            words = text.split()
            if not words:
                sys.exit("エラー: 単語が見つかりません。")
            converted_paths = []
            espeak_paths = []
            for i, word in enumerate(words):
                print(f"→ [{i+1}/{len(words)}] '{word}' を処理中...")
                converted, espeak_wav = process_one_utterance(word, args, tmpdir, label=f"w{i:03d}")
                converted_paths.append(converted)
                espeak_paths.append(espeak_wav)

            if args.keep_espeak_wav:
                kept = out_path.with_name(out_path.stem + "_espeak_source.wav")
                concatenate_wavs(espeak_paths, kept, gap_seconds=args.word_gap)
                print(f"  espeak中間ファイル保存: {kept}")

            concatenate_wavs(converted_paths, out_path, gap_seconds=args.word_gap)
        else:
            phoneme_text = basay_to_phoneme_text(text)
            print(f"音素: {phoneme_text}")

            espeak_wav = tmpdir / "espeak_source.wav"
            print(f"→ espeak音素合成中... ({args.espeak_backend})")
            do_synth_espeak(phoneme_text, args, espeak_wav)

            if args.keep_espeak_wav:
                kept = out_path.with_name(out_path.stem + "_espeak_source.wav")
                shutil.copyfile(espeak_wav, kept)
                print(f"  espeak中間ファイル保存: {kept}")

            vc_out_dir = tmpdir / "vc_out"
            vc_out_dir.mkdir()
            print("→ seed-vcで声質変換中（初回はモデルのダウンロードが入ります）...")
            convert_voice(
                espeak_wav, ref_wav, vc_out_dir, args.diffusion_steps,
                vc_version=args.vc_version,
                intelligibility_cfg_rate=args.intelligibility_cfg_rate,
                similarity_cfg_rate=args.similarity_cfg_rate,
                fp16=args.fp16,
            )

            produced = sorted(vc_out_dir.glob("*.wav"))
            if not produced:
                sys.exit("エラー: seed-vcが音声を生成しませんでした。")
            shutil.copyfile(produced[0], out_path)

        if not args.no_normalize:
            print("→ ラウドネス正規化中...")
            normalize_audio(out_path)

    print(f"✓ 完成: {out_path}")


if __name__ == "__main__":
    main()
