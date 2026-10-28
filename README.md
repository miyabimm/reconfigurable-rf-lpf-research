# Reconfigurable RF LPF Research

6つのLTEバンド設定に対応する、再構成可能な受動RFローパスフィルタの研究・数値解析用リポジトリです。

## Pi Codeの作業入口

- **実装・検証する範囲:** 現在割り当てられたGitHub Issueを基準にする。親Issueや過去の研究記録から作業範囲を拡張しない。
- **作業規則・承認境界:** [AGENTS.md](AGENTS.md)／[プロジェクト運用指示](project/instructions.md)。
- **ローカル環境:** [Pi Codeの取得・実行環境](project/README.md)。
- **現行RF入力:** [制約レジストリ](rf/constraints/registry.json)のactive正式JSON、[bands.csv](rf/bands.csv)、[固定S2P](rf/parasitics/)。必要な場合のみ[設計仕様](project/specification.md)を参照する。
- **実装とテスト:** [src/lpf](src/lpf/)、[scripts](scripts/)、[tests](tests/)。
- **研究の現況・代表結果:** [ロードマップ](project/roadmap.md)／[保存結果](project/results.md)。正式activeはRF-F003（試験条件とは区別）。

当面の開発はPi Codeのローカル実装・検証を中心に進めます。利用可能な探索機能は現行コードで確認し、未実装の実行器や未検証のRF性能を既成事実としません。

正式RF条件と試験条件を混同しないでください。新しい科学EXPや大規模本番探索には別途所有者承認が必要です。既存の実験原本・研究履歴は保持しますが、READMEから過去の探索結果・旧方針文書を通常の事前参照先として案内しません。必要な場合に限りIssue・PR・Git履歴や保存済みEXPを調査してください。
