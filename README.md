# basay-voice-clone

用你自己（或任何人）複製的聲音，正確地唸出巴賽語（Basay，凱達格蘭族語言）。

## 這是什麼

[VoxCPM2](https://github.com/mathruffian-dot/voxcpm2-voice-cloner) 是很好用的中文／英文聲音複製工具，但它沒學過巴賽語，直接餵巴賽語文字進去會發音崩潰（亂讀、漏字、無限重試）。

本專案是一個橋接工具，把巴賽語的「正確發音」跟「你的聲音」分開處理，最後合而為一：

```
巴賽語表記
   │
   ▼ basay_text.py（巴賽語音素轉換規則）
espeak 音素文字
   │
   ▼ basay.tw 正式合成服務（https://inkuei-basaytts.hf.space/）
   │  ── 跟 https://basay.tw/dictionary/ 用的是同一套引擎，發音正確可靠
機械人聲（內容正確，音色是espeak的）
   │
   ▼ seed-vc（聲音轉換）
最終輸出（內容正確，音色是你複製的聲音）
```

## 為什麼這樣設計

- **發音正確性**：巴賽語的音韻規則（含1936年Asai調查記錄的Trobiawan聲學重建）已經在 [basay.tw](https://basay.tw) 專案中建立並持續維護，直接重用其正式服務最可靠，不必在每台機器上各自編譯維護 espeak-ng。
- **聲音是你的**：espeak合成出來的是機械人聲，透過 [seed-vc](https://github.com/Plachtaa/seed-vc)（零樣本聲音轉換）轉換音色，得到「用你的聲音說巴賽語」的效果。
- **跨平台**：合成這端走遠端API，不需要在Windows/Mac/Linux各自編譯espeak-ng。

## 需求

- 一份已安裝好的 [voxcpm2-voice-cloner](https://github.com/mathruffian-dot/voxcpm2-voice-cloner)（提供 `voices/<名稱>/ref_voice.wav` 複製聲音資料）
- Python 3.10+、ffmpeg
- 網路連線（呼叫 basay.tw 的 Hugging Face Space）

詳細安裝步驟見 [SETUP.md](SETUP.md)。

## 用法

```bash
# 在 voxcpm2-voice-cloner 專案目錄下（這個repo放在子資料夾，例如 basay/）
python basay/basay_clone.py "Makawas ita mau Basay" --voice <你的複製聲音名稱>
```

輸出預設存在 `output/basay_cloned.wav`。

常用參數：

| 參數 | 說明 |
|---|---|
| `--espeak-voice` | `tai/bsystd`（台語適配・預設，聲音轉換後內容較穩）或 `tai/bsy`（Ipay歷史復原・音韻更精確） |
| `--espeak-backend` | `remote`（預設，呼叫basay.tw正式服務）或 `local`（本機編譯的espeak-ng，見SETUP.md） |
| `--vc-version` | `v1`（預設）或 `v2`（可用 `--intelligibility-cfg-rate` 直接調整發音清晰度） |
| `--per-word` | 逐字分開合成再接起來，碰到子音被seed-vc吃掉/變質時可以試試 |
| `--no-normalize` | 跳過輸出端的音量正規化（預設會用跟basay.tw一樣的loudnorm基準） |
| `--keep-espeak-wav` | 保留聲音轉換前的espeak機械人聲，方便比對問題出在哪一段 |

執行 `python basay/basay_clone.py --help` 看完整參數列表。

## 已知限制

- seed-vc是2024年的零樣本聲音轉換模型，對短詞、不常見子音組合（巴賽語的音韻跟seed-vc訓練時看過的中文/英文不完全一樣）偶爾會誤判內容（子音脫落、母音替換等）。`tai/bsystd` + `--vc-version v1` + fp32（已是預設值）目前測試起來最穩定。
- 參考聲音（`ref_voice.wav`）的錄音品質與發音清晰度，會直接影響複製後的清晰度——這是聲音複製本身的特性，不是bug。

## 授權

本repo程式碼採 MIT License（見 [LICENSE](LICENSE)）。

依賴專案各自授權：[seed-vc](https://github.com/Plachtaa/seed-vc)（GPL-3.0，本repo不內附其原始碼，只附修改用的patch，需自行clone）、[VoxCPM2](https://github.com/OpenBMB/VoxCPM)（Apache-2.0）、[voxcpm2-voice-cloner](https://github.com/mathruffian-dot/voxcpm2-voice-cloner)（MIT）。`basay_text.py` 取自 [basay-tw](https://github.com/ctotsai-hub/basay-tw) 專案（MIT）。
