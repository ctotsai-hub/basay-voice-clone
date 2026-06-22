# 安裝步驟

前提：你已經依照 [voxcpm2-voice-cloner](https://github.com/mathruffian-dot/voxcpm2-voice-cloner) 的說明，
裝好 `.venv` 並至少錄好/準備好一個 `voices/<名稱>/ref_voice.wav`。

## 1. 把本repo放進 voxcpm2-voice-cloner 的子資料夾

```bash
cd /path/to/voxcpm2-voice-cloner
git clone https://github.com/<你的帳號>/basay-voice-clone.git basay
```

（資料夾名稱用 `basay` 即可，`basay_clone.py`內部是用相對路徑找上層的`voices/`）

## 2. 安裝 gradio_client（呼叫 basay.tw 正式合成服務用）

```bash
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install gradio_client
```

## 3. 安裝 ffmpeg（輸出端音量正規化用）

- macOS: `brew install ffmpeg`
- Windows: `winget install ffmpeg`（或自行下載並加入PATH）
- Linux: `apt install ffmpeg` 等

沒裝也能跑，只是會跳過正規化並顯示警告。

## 4. 安裝 seed-vc（聲音轉換）

獨立建一個venv，避免跟VoxCPM2本身的相依套件版本衝突：

```bash
cd basay
git clone https://github.com/Plachtaa/seed-vc.git
cd seed-vc
python3 -m venv .venv-seedvc
source .venv-seedvc/bin/activate      # Windows: .venv-seedvc\Scripts\activate

# macOS:
pip install -r requirements-mac.txt
# Windows / Linux（有NVIDIA GPU可用CUDA版torch較快）:
# pip install -r requirements.txt

deactivate
```

### 套用修正patch

seed-vc原始碼有兩個已知問題（新版torchaudio存檔失敗、Mac MPS下fp16音質劣化），
本repo的 `patches/` 內附修正：

```bash
cd seed-vc
patch -p1 < ../patches/inference.py.patch
patch -p1 < ../patches/inference_v2.py.patch
cd ..
```

（Windows若沒有`patch`指令，可用Git Bash執行，或手動對照patch內容修改對應行）

## 5. 測試

```bash
cd /path/to/voxcpm2-voice-cloner
source .venv/bin/activate
python basay/basay_clone.py "Makawas ita mau Basay" --voice <你的複製聲音名稱>
```

成功會在 `output/basay_cloned.wav` 產生結果。第一次執行seed-vc會自動從
Hugging Face下載模型權重（約1.5GB）。

## 疑難排解

- `espeak-ngが見つかりません` → 你用了 `--espeak-backend local`，但沒有本機編譯
  espeak-ng。預設的 `remote` backend不需要這個，建議直接拿掉這個參數。
- `seed-vc用venvが見つかりません` → 確認步驟4的 `.venv-seedvc` 是否建在
  `basay/seed-vc/.venv-seedvc`
- 子音變質/脫落（如 m→n、k消失）→ 預設`tai/bsystd`已是測試起來最穩定的組合，
  也可以試 `--per-word`
- 音質濁/糊 → 確認沒加 `--fp16`（預設fp32，MPS上fp16容易劣化）
- 想比對espeak原始發音是否正確 → 加 `--keep-espeak-wav`

## （選用）本機espeak-ng backend

如果想完全離線（不呼叫basay.tw的Space），可以自行編譯espeak-ng並改用
`--espeak-backend local`。需要 `tai/bsy` / `tai/bsystd` 的語言定義檔
（`lang/tai/bsy`、`voices/!v/bsy`、`dictsource/bsy_rules`、`bsy_list`等），
這些定義檔目前維護在 [basay-tw](https://github.com/ctotsai-hub/basay-tw) 專案，
請洽該repo取得並用CMake編譯espeak-ng（`cmake --build <dir> --target data`），
編譯完成的資料夾路徑設給 `basay_clone.py`內的`ESPEAK_BUILD_DIR`。
