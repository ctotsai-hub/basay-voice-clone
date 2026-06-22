## 用你自己的聲音，說一句巴賽語

<span class="basay">Makawas ita mau Basay</span>——這句話，從今天起，可以用「你自己的聲音」唸出來了。

我們把巴賽語語音合成（[basay.tw 語音合成](https://inkuei-basaytts.hf.space/)）跟開源的聲音複製技術接起來，做成一個小工具：**basay-voice-clone**。簡單說，流程是這樣的：

1. 你錄一小段（或借用任何AI合成的）自己的聲音當「音色樣本」
2. 打入想說的巴賽語句子
3. 工具先用 basay.tw 正式的合成引擎，把句子轉成「發音正確」的機械人聲（跟[辭典頁面](https://basay.tw/dictionary/)用的是同一套引擎）
4. 再用聲音轉換技術，把這段機械人聲換成「你的音色」

結果就是：發音是巴賽語研究累積下來的成果（含1936年Asai調查記錄的Trobiawan方言聲學重建），但聲音是你的。

### 為什麼要做這個

巴賽語不是現有商業AI語音工具學過的語言，直接把巴賽語文字餵給市面上的聲音複製模型，常常會發音亂掉、漏字、甚至卡住重試。但 basay.tw 已經有一套累積多年、持續維護的發音規則跟合成引擎——沒有理由每個人各自重新發明一次。

所以這個工具不是「重新做一個巴賽語TTS」，而是「把已經做好的發音引擎，接上聲音複製」，讓研究者、學習者、甚至族人後裔，可以用自己（或長輩、家人）的聲音，留下巴賽語的聲音紀錄。

### 技術上在做什麼（給開發者看）

工具開源在 GitHub：**[ctotsai-hub/basay-voice-clone](https://github.com/ctotsai-hub/basay-voice-clone)**

- 巴賽語表記 → 音素文字：沿用 [basay-tw](https://github.com/ctotsai-hub/basay-tw) 的 `basay_text.py` 轉換規則
- 音素文字 → 機械人聲：呼叫 [basay.tw 語音合成 Space](https://inkuei-basaytts.hf.space/) 的API（跟辭典頁同一套espeak-ng自製音聲定義）
- 機械人聲 → 你的聲音：用 [seed-vc](https://github.com/Plachtaa/seed-vc)（零樣本聲音轉換模型）做音色轉換
- 聲音複製本體可搭配 [VoxCPM2](https://github.com/OpenBMB/VoxCPM) 等開源工具

詳細安裝與使用方式請見repo內的 README / SETUP。

### 試試看

> mataru Basay — 我們（需要）巴賽語。

歡迎拿自己的聲音，或長輩的聲音，唸一句巴賽語留下來。有問題或想法，歡迎到 GitHub repo 開 issue 討論。
