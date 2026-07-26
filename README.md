# talkrobo — 子供とおしゃべりできる人形ロボット

Claude API を頭脳に、ローカルの音声認識（faster-whisper）と音声合成（VOICEVOX）を
組み合わせた、子供向けの会話ロボットです。

ボタンを押して話しかけると、**0.3 秒で相づちが返り、2 秒以内に返事がはじまります。**
しっぽを振り、ほっぺを光らせながら、設定した子供の名前で呼びかけます。

```
 [ボタンを押して話す] → 録音 → 音声認識 → Claude → 文ごとに合成 → 再生
                          ↓         ↓                      ↓
                     目=青点滅  「ピカ？」と相づち     しっぽ・目・ほっぺが連動
```

---

## ⚠️ はじめに（大切なこと）

- **本プロジェクトは個人利用の自作を前提としています。**
  同梱の既定ペルソナはピカチュウですが、ピカチュウの名称・外観・世界観は
  **株式会社ポケモン／任天堂の権利対象**です。配布・販売・公開展示・動画公開などを
  行う場合は権利者の許諾が必要です。
- **声は原作の音声ではありません。** VOICEVOX の合成音声のピッチ・話速を調整して
  「高くて元気な声」に寄せたものです。
- **VOICEVOX は音声ライブラリごとに利用規約が異なり、クレジット表記が必要です。**
  使用する話者の規約を必ず確認してください。
- 子供の名前・会話ログ・プロフィールは**すべて手元の `data/` に保存**され、
  外部に出るのは Claude API へ送るシステムプロンプトだけです。

キャラクターの定義はすべて `config/personas/*.yaml` にあり、コード側には
キャラクター固有のロジックがありません。別のキャラクターに差し替えることもできます。

---

## できること

| | |
|---|---|
| 🗣 **会話** | Claude と会話。返事は2〜3文、ひらがな中心で6歳児にも分かることばで話す |
| ⚡ **キャラクター維持** | 鳴き声を混ぜ、技や好物を話題にし、子供を**名前で**呼ぶ |
| 👂 **相づち** | 考えている間も「ピカ？」「え〜っとね…」と間をつなぎ、沈黙を作らない |
| 🐕 **からだ** | 感情に応じてしっぽ・首サーボ、目・ほっぺの LED が動く |
| 🎤 **名前を覚える** | 初回起動時に音声で名前を聞き、以後ずっとその名前で呼ぶ |
| 🧠 **記憶** | 会話の終わりに「子供が教えてくれたこと」を抽出し、次回に引き継ぐ |
| 👨‍👩‍👧 **保護者機能** | 会話ログ、1日の利用時間制限、おやすみ時間帯、月次の API 予算上限 |

---

## 必要なもの

### ソフトウェアだけで試す場合（推奨の出発点）

- Python 3.11 以上
- Anthropic API キー（[console.anthropic.com](https://console.anthropic.com/)）

これだけで `--text` のテキスト会話が動きます。マイクもスピーカーも不要です。

### 音声で会話する場合

- 上記に加えて、マイクとスピーカー
- Docker（VOICEVOX ENGINE を動かすため）

### Raspberry Pi 実機

| 部品 | 備考 |
|---|---|
| Raspberry Pi 5（または 4） | Pi 4 では音声認識モデルを `base` に落とすこと |
| USB マイク | ReSpeaker 2-Mics HAT などでも可 |
| スピーカー | 小型アンプ内蔵のもの |
| SG90 サーボ ×2 | しっぽ・首 |
| WS2812B (NeoPixel) ×4 | 目 ×2、ほっぺ ×2 |
| 押しボタン ×1 | 子供が押しやすい大きめのもの |
| **サーボ用の 5V 電源** | Pi の 5V から取ると電圧が落ちて動作が不安定になります。別電源にして GND を共通に |
| ぬいぐるみ | 中身をくり抜いて組み込む |

---

## セットアップ

### 1. まずテキストで動かす（5分）

```bash
git clone https://github.com/IsamuTakiguchi/talkrobo.git
cd talkrobo

pip install -e ".[dev]"

cp .env.example .env                          # ANTHROPIC_API_KEY を書き込む
cp config/config.example.yaml config/config.yaml

python -m talkrobo --text
```

`config.yaml` の `child.name` が空のままなら、最初に名前を聞かれます。

### 2. 音声で会話する

VOICEVOX ENGINE を起動してから、音声モードで実行します。

```bash
docker run -d -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu20.04-latest

pip install -e ".[audio]"
python -m talkrobo --mock
```

- 初回は音声認識モデルのダウンロードと、相づちの事前合成で少し時間がかかります。
- Enter を押すと録音が始まり、**話し終えて1秒黙ると自動で止まります。**
- マイク／スピーカーが選ばれない場合は `python -m talkrobo --devices` で
  デバイス番号を調べ、`config.yaml` の `audio.input_device` / `output_device` に設定します。

Linux で `PortAudio library not found` と出る場合:

```bash
sudo apt install -y libportaudio2 libsndfile1
```

### 3. Raspberry Pi 実機

```bash
sudo apt install -y libportaudio2 libsndfile1
pip install -e ".[audio,pi]"
python -m talkrobo          # フラグ無し = 実機モード
```

配線（BCM ピン番号。`config.yaml` の `hardware` で変更できます）:

```
  押しボタン ──── GPIO17 ──┐          （内部プルアップを使用。もう片方は GND へ）
                           └── GND

  しっぽサーボ ── GPIO18 (信号)
  首サーボ ────── GPIO27 (信号)
        サーボの赤 → 別電源の +5V   ← Pi の 5V からは取らない
        サーボの茶 → 別電源の GND  ＋ Pi の GND（共通にすること）

  目の NeoPixel ──── GPIO12 (DIN)   ※ PWM が使えるピン
  ほっぺの NeoPixel ─ GPIO13 (DIN)
        NeoPixel の +5V は別電源から。GND は Pi と共通に
```

> NeoPixel は `/dev/mem` へのアクセスに root 権限が必要なことがあります。
> 動かない場合は `sudo` で実行するか、ユーザーを `gpio` グループに追加してください。

自動起動させる場合は `scripts/systemd/talkrobo.service` を参照してください。

---

## 使い方

```bash
python -m talkrobo --text     # テキストで会話（音声・ハード不要）
python -m talkrobo --mock     # PC のマイク／スピーカーで音声会話
python -m talkrobo            # Raspberry Pi 実機（ボタン・サーボ・LED）

python -m talkrobo --setup    # 名前を設定しなおす
python -m talkrobo --usage    # 今月の API 使用量を表示
python -m talkrobo --devices  # オーディオデバイス一覧
```

会話を終えるときは「ばいばい」と言う（または Ctrl-C）。

---

## 設定

`config/config.yaml` の主な項目です。

### 子供の名前

```yaml
child:
  name: "はると"      # 空なら初回に音声で聞く
  reading: "ハルト"   # 省略可。音声合成に渡す読み
  honorific: "くん"   # くん / ちゃん / "" (呼び捨て)
  age: 6              # ことばの難しさの調整に使う
```

音声で聞く場合の流れ:

1. 「きみのなまえは なんていうの？」
2. 子供が答える → 音声認識の結果を Claude が正規化（「春人です」→ `はると` / `ハルト`）
3. **合成音声で読み上げて本人に確認**（OK が出た読みだけを採用するので、読み間違いが残らない）
4. 「くん」か「ちゃん」かを選ぶ
5. `data/profile.json` に保存

3回聞き取れなかった場合は「きみ」と呼んで会話を続け、`config.yaml` での設定を促します。

### モデル（コストに直結）

```yaml
llm:
  model: "claude-haiku-4-5"   # claude-sonnet-5 / claude-opus-5 に変更可
  max_tokens: 300
  history_turns: 8            # 送る直近ターン数。減らすと安くなる
```

### 保護者向けの上限

```yaml
limits:
  daily_limit_minutes: 30     # 0 で無制限
  quiet_start: "20:00"        # おやすみ時間帯（この間は反応しない）
  quiet_end: "07:00"

budget:
  monthly_yen: 1000           # 0 で無制限
  warn_at_percent: 80
```

上限に達すると、エラー画面ではなく**ピカチュウが「ねむくなっちゃった」と言って終わります。**
子供に不具合を見せないための設計です。

### 声（VOICEVOX の話者）

`config/personas/pikachu.yaml` の `voice` で変更します。

```yaml
voice:
  speaker_id: 3
  speed: 1.15       # 話速。上げると元気に聞こえる
  pitch: 0.08       # 高さ。上げると子供っぽくなる
  intonation: 1.2   # 抑揚
```

使える話者 ID は環境の VOICEVOX に問い合わせて確認してください（バージョンによって
異なります）。高めで元気な声が向いています。

```bash
curl -s localhost:50021/speakers \
  | python -c "import json,sys; [print(f\"{s['name']}: \" + ', '.join(f\"{t['name']}={t['id']}\" for t in s['styles'])) for s in json.load(sys.stdin)]"
```

`speaker_id` や `speed` を変えると、相づちの音声キャッシュは自動で作り直されます。

---

## ランニングコスト

課金されるのは **Claude API だけ**です。音声認識も音声合成もローカル実行なので
追加費用はかかりません。

1ターン = 子供の発話1回 + 返事1回。$1=155円で計算した目安:

| モデル | 20ターン/日 | **40ターン/日** | 80ターン/日 |
|---|---|---|---|
| **claude-haiku-4-5**（既定） | 約270円/月 | **約530円/月** | 約1,060円/月 |
| claude-sonnet-5 | 約800円/月 | 約1,600円/月 | 約3,300円/月 |
| claude-opus-5 | 約1,100円/月 | 約2,100円/月 | 約4,200円/月 |

自分の設定での実測値は次のコマンドで出せます（日本語のトークン数は推定が
当てにならないので、`count_tokens` で実測します）。

```bash
python scripts/cost_estimate.py
```

> Haiku 4.5 はプロンプトキャッシュの最小長が 4,096 トークンで、本システムプロンプト
> （約1,400トークン）では**キャッシュが効きません**。埋め草で水増しすると品質が落ちる
> うえ入力トークンも増えるため、キャッシュ無し前提で設計しています。
> Opus 5 / Sonnet 5 に切り替えると自動でキャッシュが有効になります。

---

## 保護者の方へ

- **会話ログ**: `data/logs/YYYY-MM-DD.jsonl`（1行1発言。`role` が `child` / `robot`）
- **子供のプロフィール**: `data/profile.json`（名前と、ロボットが覚えたこと。
  中身を見て、消したい項目を削除できます）
- **API 使用量**: `data/usage.jsonl` / `python -m talkrobo --usage`
- **遊んだ時間**: `data/playtime.json`

これらはすべて手元にのみ保存されます。`data/` は `.gitignore` に入っています。

ロボットには次の安全ルールがシステムプロンプトとして常に適用されます（ペルソナを
差し替えても消えないよう、コード側 `src/talkrobo/persona.py` に置いてあります）。

- こわい話・ざんこくな話・性的な話をしない
- 住所・電話番号・学校名などを聞き出さない
- 買い物やアプリのインストールを勧めない
- 危ないことのやり方を教えず、「おうちのひとといっしょにね」と伝える
- 子供がつらいことを話したら受けとめ、大人に相談するよう促す
- 「おうちのひとよりボクのほうがいいよ」のようなことを言わない
- 分からないことは「わからないなあ」と正直に言う
- 自分は乱暴な言葉を使わず、子供が使っても真似しない。
  **叱りつけず、悲しそうに1回だけ**「そのことば、ボクちょっとかなしいな」と伝えて
  遊びに戻る（毎回説教すると逆効果なので繰り返さない）。
  人を傷つける言葉を誰かに向けて繰り返す場合だけ、大人に相談するよう促す

---

## 開発

```bash
pytest -q                      # テスト（API・マイク・GPIO なしで完結）
ruff check src tests           # 静的チェック
ruff format src tests          # 整形

python scripts/persona_check.py   # キャラクター維持を20問で採点（3文まで・漢字なし・名前1回 など）
python scripts/latency_check.py   # 返事までの時間を実測
python scripts/cost_estimate.py   # 実トークン数から月額を試算
```

### 設計のポイント

- **文が確定した時点で喋りはじめる。** Claude の応答をストリーミングで受け、
  `。！？` が来るたびに音声合成キューへ流します。全文の生成は待ちません。
- **相づちは事前合成。** 都度合成では「間」に間に合わないので、起動時に
  ペルソナのセリフをまとめて合成し `data/cache/fillers/` に置きます。再生開始は実質 0 秒です。
- **感情は返事の先頭タグで受け取る。** `[うれしい]ピカ！…` の形式にすることで、
  ツール呼び出しの往復を増やさずに、しっぽや LED を声と同時に動かせます。
- **モデル世代差は capability テーブルで吸収。** Haiku 4.5 と Opus 5 では
  thinking・effort・キャッシュ最小長の仕様が違い、間違えると 400 エラーになります
  （`src/talkrobo/llm/client.py`）。
- **からだは専用スレッド。** サーボや LED の制御が会話ループを止めないようにしています。

### ディレクトリ

```
config/
  config.example.yaml      設定のひな型
  personas/pikachu.yaml    キャラクター定義（口調・鳴き声・声・感情→動き）
src/talkrobo/
  app.py                   会話ループ
  persona.py               ペルソナ→システムプロンプト（安全ルールもここ）
  runtime.py               音声モードの部品組み立て
  llm/                     Claude 呼び出し・文分割・感情タグ・記憶・名前
  audio/                   録音・再生・相づち
  stt/  tts/               音声認識・音声合成（差し替え可能）
  hardware/                からだ（実機／画面表示）とボタン
  parental/                会話ログ・利用時間・予算
```

---

## うまくいかないとき

| 症状 | 対処 |
|---|---|
| `ANTHROPIC_API_KEY が設定されていません` | `cp .env.example .env` して API キーを記入 |
| `VOICEVOX ENGINE に接続できません` | `docker run -d -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu20.04-latest` |
| `PortAudio library not found`（Linux） | `sudo apt install -y libportaudio2 libsndfile1` |
| `cannot load library ...libportaudioarm64.dll` | ARM 版 Windows（Copilot+ PC など）で起きます。`git pull` で最新にすれば自動で回避されます（`src/talkrobo/audio/_win_arm.py`）。なお ARM 版 Windows では音声認識が x64 エミュレーションで動くため遅く、`stt.model_size` を `base` にするのがおすすめです |
| 返事が遅い | `stt.model_size` を `base` に、`llm.model` を `claude-haiku-4-5` に |
| 名前を間違えて覚えた | `python -m talkrobo --setup` で聞き直す |
| 録音がすぐ止まる／止まらない | `audio` の入力デバイスを確認。周囲がうるさい場合は `src/talkrobo/audio/recorder.py` の `DEFAULT_SILENCE_RMS` を調整 |
| サーボがじりじり鳴る | サーボ用の電源を Pi と分け、GND を共通にする |
| キャラクターが崩れる | `python scripts/persona_check.py` で計測し、ペルソナの `speech_style` / `cry_rule` を調整 |

---

## ライセンス

コードは個人利用を想定しています。既定ペルソナが参照するキャラクターおよび
VOICEVOX の音声ライブラリについては、それぞれの権利者の規約に従ってください。
