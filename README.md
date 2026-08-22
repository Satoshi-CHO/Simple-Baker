# Simple Baker

## English

Simple Baker makes Blender's standard Cycles baking workflow easier to approach.

Blender's built-in baking system is powerful, but preparing a bake can require several manual steps: choosing the correct objects, setting the active object, creating and selecting Image Texture nodes, configuring output settings, and repeating the process for each map. These steps can be difficult to understand, especially for users who are new to baking.

Simple Baker reduces this setup work while keeping Blender's standard baking behavior at its core. You explicitly choose the bake target and, when transferring data, the source model(s) in the add-on UI. The add-on prepares the required selection and Image Texture nodes, runs Blender's built-in bake operation, and saves the selected maps in sequence.

### What Simple Baker is for

- Learning and using Blender's standard Cycles bake workflow with less setup overhead
- Baking a model itself or transferring maps from one or more source models
- Creating the required Image Texture nodes and object selection automatically
- Saving several selected map types with consistent settings

### What Simple Baker is not for

Simple Baker is not designed as a high-volume production baking system. If you need large batch jobs, extensive pipeline automation, UDIM production, or highly specialized baking features, consider an add-on designed specifically for those workflows.

The goal is not to replace Blender's Bake settings. It is to preserve their familiar behavior while removing repetitive node-creation and object-selection work.

### Compatibility

- Supported Blender versions: 5.0.0 and later
- Tested with: Blender 5.0.1, Blender 5.1.2, and Blender 5.2.0 LTS
- Render engine: Cycles. The add-on switches to Cycles only while baking and restores the previous engine afterwards.
- Not supported: Blender 4.x, batch baking multiple low-poly sets, UDIM, and automatic UV unwrapping

### Features

- **Bake This Model** and **Transfer From Other Models** workflows. In transfer mode, source model(s) and the bake target are explicitly selected in the add-on UI.
- Eleven output maps: Combined, AO, Shadow, Normal, UV, Roughness, Emit, Environment, Diffuse, Glossy, and Transmission
- PNG (8/16-bit), Targa (8-bit), and OpenEXR (16/32-bit) output
- OpenGL, DirectX, and Custom normal-map formats
- Temporary Image Texture nodes or nodes retained in the material
- Protection for existing Principled input links and confirmation before overwriting existing files

### Installation

1. Download `simple_baker-vX.Y.Z.zip` from the [Releases](../../releases) page.
2. In Blender, open **Edit > Preferences > Get Extensions** and select **Install from Disk** from the menu.
3. Select the downloaded ZIP file, then enable **Simple Baker**.

Changes to Blender nodes, materials, and images can be undone in Blender. Files overwritten on disk cannot be restored with Blender's Undo command.

---

## 日本語

Simple Baker は、Blender 標準の Cycles ベイク機能を、より取り組みやすくするためのアドオンです。

Blender 標準のベイク機能は強力ですが、実行前には複数の手作業が必要になります。正しいオブジェクトを選択し、アクティブオブジェクトを設定し、Image Texture ノードを作成・選択し、出力設定を整え、マップごとに同様の作業を繰り返す必要があります。これらは、特にベイクに慣れていない方にとって理解や操作の負担になりやすい部分です。

Simple Baker は、Blender 標準のベイク動作を中心に保ちながら、この準備作業を減らします。ベイク先モデルと、転写時の転写元モデルをアドオン UI で明示的に指定すると、必要なオブジェクト選択と Image Texture ノードの準備を行い、Blender 標準のベイク処理を実行して、選択したマップを連続保存します。

### Simple Baker が目指すこと

- Blender 標準の Cycles ベイクを、少ない準備作業で学び・利用できるようにする
- モデル自身へのベイクと、1 個以上の別モデルからの転写を扱う
- 必要な Image Texture ノードの作成とオブジェクト選択を自動化する
- 選択した複数のマップを、統一した設定で保存する

### Simple Baker が目指さないこと

Simple Baker は、大量処理を中心としたプロダクション向けベイクシステムではありません。大規模なバッチ処理、広範なパイプライン自動化、UDIM 制作、より専門的なベイク機能が必要な場合は、それらを主目的とする別のアドオンを検討してください。

目的は Blender の Bake 設定を置き換えることではありません。標準機能の挙動をできるだけ維持しつつ、繰り返し発生するノード作成とオブジェクト選択の手間を減らすことです。

### 対応状況

- 対応 Blender: 5.0.0 以降
- 実機検証済み: Blender 5.0.1、Blender 5.1.2、Blender 5.2.0 LTS
- レンダーエンジン: Cycles。ベイク中のみ Cycles に切り替え、完了後に元のエンジンへ戻します。
- 対象外: Blender 4 系、複数ローポリセットの一括ベイク、UDIM、UV 自動展開

### 主な機能

- 「このモデルをベイク」と「別のモデルから転写」の 2 モード。転写では、転写元モデル（複数可）とベイク先モデルをアドオン UI で明示的に指定できます。
- Combined、AO、Shadow、Normal、UV、Roughness、Emit、Environment、Diffuse、Glossy、Transmission の 11 マップ
- PNG（8/16 bit）、Targa（8 bit）、OpenEXR（16/32 bit）への保存
- OpenGL、DirectX、Custom のノーマルマップ形式
- 一時的な Image Texture ノード、またはマテリアルに残すノードの選択
- 既存の Principled 入力リンクを保護し、既存ファイルの上書きを確認

### 導入方法

1. [Releases](../../releases) ページから `simple_baker-vX.Y.Z.zip` をダウンロードします。
2. Blender で **Edit > Preferences > Get Extensions** を開き、メニューから **Install from Disk** を選びます。
3. ダウンロードした ZIP を指定し、**Simple Baker** を有効にします。

Blender 内のノード・マテリアル・画像の変更は Undo の対象です。一方、ディスクに上書きした出力ファイルは Blender の Undo では復元できません。

---

## Developer Verification / 開発者向け検証

```sh
python tests/test_pure_logic.py
blender --background --factory-startup --python tests/run_all.py
```

Run the Blender integration suite with each supported Blender version before a release. The suite covers self-baking, UI-selected model transfer, multiple materials, all eleven maps, output formats, invalid input, overwrite protection, re-baking with retained nodes, and recovery from save failures.

リリース前には、対応する各 Blender バージョンで実機回帰スイートを実行します。自己ベイク、UI 指定によるモデル間転写、複数マテリアル、全 11 マップ、保存形式、異常入力、上書き保護、保持ノードを使う再ベイク、保存失敗時の復旧を確認します。

## License / ライセンス

Copyright (C) 2026 Satoshi CHO

Simple Baker is licensed under the GNU General Public License, version 3 or (at your option) any later version. See [LICENSE](LICENSE) for the full license text.

Simple Baker は GNU General Public License のバージョン 3、または（利用者の選択により）それ以降のバージョンの条件で利用できます。ライセンス全文は [LICENSE](LICENSE) を参照してください。
