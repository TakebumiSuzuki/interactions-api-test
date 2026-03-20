"""
deep_research.py
────────────────────────────────────────────────────────────────
Deep Research Agent でウェブ調査を行い、結果をローカルファイルに保存する。

使い方:
    # 1. ライブラリをインストール
    pip install google-genai --upgrade

    # 2. APIキーを環境変数に設定
    export GEMINI_API_KEY="your_api_key_here"   # Mac/Linux
    set    GEMINI_API_KEY=your_api_key_here      # Windows

    # 3. 実行（トピックは引数で渡す。省略するとデフォルトトピックを使用）
    python deep_research.py "EVバッテリー市場の競合分析"
    python deep_research.py  # 引数なしでもOK
────────────────────────────────────────────────────────────────
"""

import os
import sys
import time
import datetime


# ─────────────────────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────────────────────

# 引数でトピックを渡せる。なければデフォルトを使用。
DEFAULT_TOPIC = "EV電池市場の競合分析を簡単にしてください。全体像だけシンプルに教えてもらえれば良いです。"
TOPIC = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TOPIC

# 出力ディレクトリ（スクリプトと同じ場所に "results" フォルダを作る）
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# ポーリング設定
POLL_INTERVAL_INITIAL = 15   # 最初のポーリング間隔（秒）
POLL_INTERVAL_MAX     = 60   # ポーリング間隔の上限（秒）
TIMEOUT_MINUTES       = 65   # この時間を超えたらタイムアウトエラー
MAX_CONSECUTIVE_ERRORS = 10


# ─────────────────────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────────────────────
def main():
    # ── 依存チェック ──────────────────────────────────────────
    try:
        from google import genai
    except ImportError:
        sys.exit(
            "エラー: google-genai がインストールされていません。\n"
            "  pip install google-genai --upgrade  を実行してください。"
        )

    # ── APIキー確認 ───────────────────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit(
            "エラー: 環境変数 GEMINI_API_KEY が設定されていません。\n"
            "  export GEMINI_API_KEY='your_api_key'  を実行してください。"
        )

    client = genai.Client(api_key=api_key)

    # ── ステップ 1: Deep Research 起動 ────────────────────────
    print("=" * 60)
    print(f"トピック : {TOPIC}")
    print("=" * 60)
    print("[1/3] Deep Research Agent を起動します...")

    interaction = client.interactions.create(
        agent="deep-research-pro-preview-12-2025",
        input=TOPIC,
        background=True,  # 非同期実行（必須）
        store=True,       # background=True のとき必須
    )
    research_id = interaction.id
    print(f"      Interaction ID : {research_id}")
    print( "      ※ 完了まで通常 5〜20 分、長くて最大 60 分かかります。")

    # ── ステップ 2: 完了をポーリングして待つ ──────────────────
    print("[2/3] 完了を待機中...")

    wait             = float(POLL_INTERVAL_INITIAL)
    elapsed          = 0.0
    max_sec          = TIMEOUT_MINUTES * 60
    consecutive_errs = 0   # ← ループ前に必ず初期化
    report           = None

    while elapsed < max_sec:
        time.sleep(wait)
        elapsed += wait
        mins, secs = divmod(int(elapsed), 60)  # ← int() で float を除去

        # ── ポーリング（500等の一時エラーはスキップしてリトライ）──
        try:
            result = client.interactions.get(research_id)
            consecutive_errs = 0  # 成功したらリセット

        except Exception as e:
            consecutive_errs += 1
            print(
                f"      [{mins:02d}:{secs:02d}経過] "
                f"一時エラー ({consecutive_errs}/{MAX_CONSECUTIVE_ERRORS})、リトライします: {e}"
            )
            if consecutive_errs >= MAX_CONSECUTIVE_ERRORS:
                sys.exit(
                    f"エラー: {MAX_CONSECUTIVE_ERRORS} 回連続エラーのため中断します。\n"
                    f"最後のエラー: {e}"
                )
            wait = min(wait * 1.5, POLL_INTERVAL_MAX)
            continue  # ← ステータス確認をスキップして次のループへ

        # ── ステータス確認 ──────────────────────────────────
        print(f"      [{mins:02d}:{secs:02d}経過] ステータス: {result.status}")

        if result.status == "completed":
            for output in reversed(result.outputs):
                if output.type == "text":
                    report = output.text
                    break
            if report is None:
                sys.exit("エラー: completed だがテキスト出力が見つかりません。")
            print("[2/3] リサーチ完了！")
            break

        elif result.status == "failed":
            sys.exit(f"エラー: リサーチが失敗しました。\n詳細: {result.error}")

        elif result.status == "cancelled":
            sys.exit("エラー: リサーチがキャンセルされました。")

        # 通常の指数バックオフ（上限 POLL_INTERVAL_MAX 秒）
        wait = min(wait * 1.5, POLL_INTERVAL_MAX)

    else:
        # while条件が False になって抜けた場合 = タイムアウト
        sys.exit(f"エラー: {TIMEOUT_MINUTES} 分経過してもリサーチが完了しませんでした。")

    # ── ステップ 3: ローカルファイルに保存 ────────────────────
    print("[3/3] 結果をファイルに保存します...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(
        c if c.isalnum() or c in ("-", "_") else "_"
        for c in TOPIC[:20]
    )
    filename    = f"{timestamp}_{safe_topic}.txt"
    output_path = os.path.join(OUTPUT_DIR, filename)

    header = (
        f"# Deep Research レポート\n"
        f"# 生成日時       : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"# トピック       : {TOPIC}\n"
        f"# Interaction ID : {research_id}\n"
        f"{'=' * 60}\n\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(report)

    print(f"      保存先 : {output_path}")
    print(f"      サイズ : {len(report):,} 文字")
    print("=" * 60)
    print("✅ 完了")


if __name__ == "__main__":
    main()
