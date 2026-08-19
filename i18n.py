"""Blender translation registration for Simple Baker."""

from __future__ import annotations

import bpy

from .constants import ADDON_ID

_DEFAULT = bpy.app.translations.contexts.default
_OPERATOR = bpy.app.translations.contexts.operator_default

# Japanese terms used in longer descriptions. Keep these aligned with the UI
# labels so translated tooltips never mix English property names into Japanese.
_JA_TERMS = {
    "base_color": "ベースカラー",
    "color": "カラー",
    "direct_lighting": "直接照明",
    "emission_color": "放射カラー",
    "indirect_lighting": "間接照明",
    "normal_input": "ノーマル入力",
    "normal_map_node": "ノーマルマップノード",
    "roughness": "粗さ",
}

TRANSLATIONS = {
    "ja_JP": {
        (_DEFAULT, "Simple Baker"): "Simple Baker",
        (_DEFAULT, "Bake Objects"): "ベイク対象",
        (_DEFAULT, "Output Maps"): "出力マップ",
        (_DEFAULT, "Output Images & Targets"): "出力画像とターゲット",
        (_DEFAULT, "Bake Settings"): "ベイク設定",
        (_DEFAULT, "Bake & Save"): "ベイクして保存",
        (_OPERATOR, "Bake & Save"): "ベイクして保存",
        (_DEFAULT, "Bake Method"): "ベイク方法",
        (_DEFAULT, "Bake This Model"): "このモデルをベイク",
        (_DEFAULT, "Bake a mesh object to itself"): "指定したメッシュオブジェクトを自身にベイクします。",
        (_DEFAULT, "Transfer From Other Models"): "別のモデルから転写",
        (_DEFAULT, "Bake source meshes onto a separate target mesh"): "転写元メッシュの情報を、別のベイク先メッシュへベイクします。",
        (_DEFAULT, "Model to Bake"): "ベイクするモデル",
        (_DEFAULT, "Source Models"): "転写元モデル",
        (_DEFAULT, "Bake Target"): "ベイク先モデル",
        (_DEFAULT, "Mesh object that receives the baked images"): "ベイクした画像を受け取るメッシュオブジェクトです。",
        (_DEFAULT, "Add Source Model"): "転写元モデルを追加",
        (_DEFAULT, "Remove Source Model"): "転写元モデルを削除",
        (_DEFAULT, "Direct Lighting"): _JA_TERMS["direct_lighting"],
        (_DEFAULT, "Light that reaches the surface without bouncing. When enabled it is included in the bake; when disabled it is excluded. Use Color alone for an unlit base-color map."): f"{_JA_TERMS['direct_lighting']}とは、他の面で反射せずに光源から表面へ届く光です。有効にするとベイク結果へ含め、無効にすると除外します。照明を含まない{_JA_TERMS['base_color']}マップが必要な場合は、{_JA_TERMS['color']}のみを有効にします。",
        (_DEFAULT, "Indirect Lighting"): _JA_TERMS["indirect_lighting"],
        (_DEFAULT, "Light that reaches the surface after one or more bounces. When enabled it is included in the bake; when disabled it is excluded."): f"{_JA_TERMS['indirect_lighting']}とは、他の面で1回以上反射してから表面へ届く光です。有効にするとベイク結果へ含め、無効にすると除外します。",
        (_DEFAULT, "Color"): _JA_TERMS["color"],
        (_DEFAULT, "The surface shader color without lighting. Color alone bakes the base color. Without Color, direct and indirect lighting are grayscale; with Color, they are baked in color."): f"照明を含まない表面シェーダーの色です。{_JA_TERMS['color']}のみを有効にすると{_JA_TERMS['base_color']}をベイクします。{_JA_TERMS['color']}を無効にすると{_JA_TERMS['direct_lighting']}と{_JA_TERMS['indirect_lighting']}はグレースケールになり、有効にすると照明色を含んだ結果になります。",
        (_DEFAULT, "Bakes materials, textures, and lighting except specularity. Use for a final-look texture; contribution settings control its contents."): "スペキュラー以外のマテリアル、テクスチャ、照明をベイクします。最終見た目用テクスチャに使え、含める要素は寄与設定で調整します。",
        (_DEFAULT, "Bakes grayscale ambient occlusion and ignores scene lights. Usually multiply with a color texture in a shader or compositor."): "グレースケールのアンビエントオクルージョンをベイクし、シーンのライトは無視します。通常はシェーダーまたはコンポジターでカラーテクスチャに乗算します。",
        (_DEFAULT, "Bakes shadows and lighting. Use for compositing or a custom lighting workflow."): "影と照明をベイクします。コンポジットや独自のライティング処理に使用します。",
        (_DEFAULT, "Bakes surface normal directions as RGB. Connect through a Normal Map node to the Principled Normal input; automatic connection is available."): f"表面法線の方向をRGB画像としてベイクします。{_JA_TERMS['normal_map_node']}経由でマテリアルの{_JA_TERMS['normal_input']}へ接続します。自動接続も利用できます。",
        (_DEFAULT, "Bakes mapped UV coordinates into red and green; blue is always 1. Use for diagnostics or custom coordinate-based shaders."): "UV座標を赤・緑チャンネルへベイクします。青チャンネルは常に1です。確認用または座標を利用するカスタムシェーダーに使用します。",
        (_DEFAULT, "Bakes the material roughness pass. Connect to Principled Roughness; automatic connection is available."): f"マテリアルの{_JA_TERMS['roughness']}をベイクします。マテリアルの{_JA_TERMS['roughness']}入力へ接続します。自動接続も利用できます。",
        (_DEFAULT, "Bakes the material emission or glow color. Connect to Principled Emission Color; automatic connection is available."): f"マテリアルの発光色をベイクします。マテリアルの{_JA_TERMS['emission_color']}入力へ接続します。自動接続も利用できます。",
        (_DEFAULT, "Bakes the scene World shader as seen by rays from the world origin. Use for compositing or a custom environment-lighting workflow."): "ワールド原点からのレイで見たシーンのWorldシェーダーをベイクします。コンポジットや独自の環境ライティング処理に使用します。",
        (_DEFAULT, "Bakes the diffuse pass. With only Color enabled it is the surface base color; connect it to Principled Base Color. Direct and Indirect add lighting."): f"ディフューズパスをベイクします。{_JA_TERMS['color']}のみを有効にすると表面の{_JA_TERMS['base_color']}になり、マテリアルの{_JA_TERMS['base_color']}入力へ接続できます。{_JA_TERMS['direct_lighting']}と{_JA_TERMS['indirect_lighting']}を有効にすると照明も加わります。",
        (_DEFAULT, "Bakes the glossy reflection pass. Use for compositing or a custom shader workflow."): "光沢反射パスをベイクします。コンポジットやカスタムシェーダーに使用します。",
        (_DEFAULT, "Bakes the transmission or refraction pass. Use for compositing or a custom shader workflow."): "透過・屈折パスをベイクします。コンポジットやカスタムシェーダーに使用します。",
        (_DEFAULT, "Common Name"): "共通名",
        (_DEFAULT, "Output Directory"): "出力フォルダー",
        (_DEFAULT, "Resolution"): "解像度",
        (_DEFAULT, "File Format"): "ファイル形式",
        (_DEFAULT, "Color Depth"): "カラー深度",
        (_DEFAULT, "Node Usage"): "ノードの利用方法",
        (_DEFAULT, "Choose whether baked results are automatically applied to the material"): "ベイク結果をマテリアルへ自動適用するかを選択します。",
        (_DEFAULT, "Keep Image Texture Nodes After Baking"): "ベイク後も画像テクスチャノードを残す",
        (_DEFAULT, "Keep baked images available in the material's node editor for later use"): "ベイクした画像を、後でマテリアルのノードエディターから確認・利用できるようにします。",
        (_DEFAULT, "Place Nodes Only"): "ノードのみ配置",
        (_DEFAULT, "Add baked images to the material's node editor without changing its appearance."): "ベイクした画像をマテリアルのノードエディターに追加します。マテリアルの見た目は変わりません。",
        (_DEFAULT, "Place Nodes and Connect to Material"): "ノードを配置してマテリアルへ接続",
        (_DEFAULT, "Automatically apply supported baked results to the material. Existing settings are kept."): "対応するベイク結果をマテリアルへ自動適用します。すでにある設定は変更しません。",
        (_DEFAULT, "Baked images are saved, but no Image Texture nodes are kept."): "ベイクした画像は保存されますが、画像テクスチャノードは残りません。",
        (_DEFAULT, "Normal Map Format"): "ノーマルマップ形式",
        (_DEFAULT, "Blender, Unity, and Godot. Tangent space: +X, +Y, +Z."): "Blender、Unity、Godot向けです。接線空間: +X、+Y、+Z。",
        (_DEFAULT, "Unreal Engine. Tangent space: +X, -Y, +Z; flips the green channel."): "Unreal Engine向けです。接線空間: +X、-Y、+Z。緑チャンネルを反転します。",
        (_DEFAULT, "Custom"): "カスタム",
        (_DEFAULT, "Configure Blender's normal space and RGB axes manually."): "Blenderの法線空間とRGB軸を手動で設定します。",
        (_DEFAULT, "Bake Target Nodes Only"): "ベイク先ノードのみ",
        (_DEFAULT, "Connect Supported Maps to Material"): "対応マップをマテリアルへ接続",
        (_DEFAULT, "Undo does not restore overwritten output files."): "Undoでは上書きした出力ファイルを復元できません。",
        (_DEFAULT, "Choose the models above, then run Bake & Save."): "上でモデルを指定してから「ベイクして保存」を実行します。",
        (_DEFAULT, "Combined Contributions"): "Combined の寄与",
        (_DEFAULT, "Surface Contributions"): "サーフェスの寄与",
        (_DEFAULT, "Select a mesh object to use as the bake target."): "ベイク先にするメッシュオブジェクトを選択してください。",
        (_DEFAULT, "Bake target '{name}' must be a mesh object."): "ベイク先「{name}」はメッシュオブジェクトである必要があります。",
        (_DEFAULT, "Bake target '{name}' has no UV map. Create one in UV Editing before baking."): "ベイク先「{name}」にUVマップがありません。UV EditingでUVマップを作成してから実行してください。",
        (_DEFAULT, "Bake target '{name}' has no material. Assign a material before baking."): "ベイク先「{name}」にマテリアルがありません。マテリアルを割り当ててから実行してください。",
        (_DEFAULT, "Choose an output directory before baking."): "ベイク前に出力フォルダーを指定してください。",
        (_DEFAULT, "Output directory does not exist: {path}"): "出力フォルダーが存在しません: {path}",
        (_DEFAULT, "Output directory is not writable: {path}"): "出力フォルダーに書き込めません: {path}",
        (_DEFAULT, "Select at least one output map before baking."): "ベイク前に少なくとも1つの出力マップを選択してください。",
        (_DEFAULT, "{depth}-bit output is not supported for {format}. Choose a supported color depth."): "{format}では{depth}ビット出力はサポートされていません。対応するカラー深度を選択してください。",
        (_DEFAULT, "Enable Keep Image Texture Nodes After Baking before connecting baked maps to materials."): "ベイク済みマップをマテリアルへ接続する前に、「ベイク後も画像テクスチャノードを残す」を有効にしてください。",
        (_DEFAULT, "Image Texture node bake target failed. Select the generated Image Texture node, or disable Keep Image Texture Nodes After Baking to use a temporary bake target."): "画像テクスチャノードをベイク先として使用できませんでした。生成された画像テクスチャノードを選択するか、「ベイク後も画像テクスチャノードを残す」を無効にして一時ベイク先を使用してください。",
        (_DEFAULT, "Choose a mesh object for every source-model entry."): "各転写元モデルの欄でメッシュオブジェクトを指定してください。",
        (_DEFAULT, "Add at least one source model before baking."): "ベイク前に少なくとも1つの転写元モデルを追加してください。",
        (_DEFAULT, "The bake target cannot also be a source model."): "ベイク先モデルを転写元モデルに指定することはできません。",
        (_DEFAULT, "Selected bake sources must be mesh objects: {names}"): "選択したベイク元はメッシュオブジェクトである必要があります: {names}",
        (_DEFAULT, "The following files already exist and will be overwritten:"): "次のファイルは既に存在し、上書きされます:",
        (_DEFAULT, "Existing output files require confirmation. Use Bake & Save from the panel."): "既存の出力ファイルには確認が必要です。パネルの「ベイクして保存」を使用してください。",
        (_DEFAULT, "No maps were baked successfully."): "ベイクに成功したマップはありません。",
        (_DEFAULT, "Saved {count} map(s)."): "{count}件のマップを保存しました。",
        (_DEFAULT, "{count} map(s) failed; successful maps were saved."): "{count}件のマップは失敗しましたが、成功したマップは保存されました。",
        (_DEFAULT, "Kept {count} existing material input connection(s) unchanged."): "既存のマテリアル入力接続 {count} 件は変更しませんでした。",
        (_DEFAULT, "Simple Baker: Preparing {count} map(s)"): "Simple Baker: {count}件のマップを準備中",
        (_DEFAULT, "Simple Baker: Baking {label} ({current}/{total})"): "Simple Baker: {label} をベイク中（{current}/{total}）",
        (_DEFAULT, "Bake selected maps and save them to disk"): "選択したマップをベイクしてディスクに保存します。",
        (_OPERATOR, "Bake selected maps and save them to disk"): "選択したマップをベイクしてディスクに保存します。",
    }
}


def register_translations() -> None:
    """Register Japanese UI strings; English uses the original message IDs."""
    bpy.app.translations.register(ADDON_ID, TRANSLATIONS)


def unregister_translations() -> None:
    """Remove add-on UI strings from Blender's translation registry."""
    bpy.app.translations.unregister(ADDON_ID)
