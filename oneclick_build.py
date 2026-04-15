#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
一键打包安装包脚本：整合 build_simple.bat、build_installer.bat、build_and_installer.bat、 一键打包.bat

功能：
- 计算版本号（基于 git 提交次数），写入 version.txt
- 检查/安装 PyInstaller 并进行打包
- 复制额外资源到 dist\res
- 自动生成 Inno Setup 脚本并查找 iscc.exe 编译安装包

使用：
    python oneclick_build.py            # 打包并生成安装包（若检测到 Inno Setup）
    python oneclick_build.py --dry-run  # 试运行，仅打印步骤

注意：
- 若未安装 Inno Setup，将只完成可执行文件打包并友好提示。
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def normalize_windows_path(path) -> str:
    """移除 Windows 扩展长路径前缀，避免部分外部工具解析失败。"""
    raw = str(path)
    if os.name != "nt":
        return raw
    if raw.startswith("\\\\?\\UNC\\"):
        return "\\\\" + raw[8:]
    if raw.startswith("\\\\?\\"):
        return raw[4:]
    return raw


ROOT = Path(normalize_windows_path(Path(__file__).resolve().parent))
APP_NAME = "Gavin_com"
APP_PUBLISHER = "Gavin"
APP_DESCRIPTION = "Gavin COM 串口调试助手"
# Inno Setup AppId GUID（不含花括号）
APP_ID_GUID = "B5A28A9E-8C2D-4F8A-8D7C-1D9E022A9A9A"


def print_step(msg: str):
    print(f"\n===== {msg} =====")


def run(cmd, cwd=None, check=True, capture=False):
    if isinstance(cmd, list):
        normalized_cmd = [normalize_windows_path(x) if isinstance(x, (str, os.PathLike)) else x for x in cmd]
        printable = " ".join(map(str, normalized_cmd))
    else:
        normalized_cmd = normalize_windows_path(cmd) if isinstance(cmd, (str, os.PathLike)) else cmd
        printable = normalized_cmd
    if cwd is not None:
        cwd = normalize_windows_path(cwd)
    print(f"> {printable}")
    if capture:
        r = subprocess.run(normalized_cmd, cwd=cwd, capture_output=True, text=True, shell=isinstance(normalized_cmd, str))
        if check and r.returncode != 0:
            print(r.stdout)
            print(r.stderr)
            raise RuntimeError(f"命令执行失败: {printable}")
        return r
    else:
        r = subprocess.run(normalized_cmd, cwd=cwd, shell=isinstance(normalized_cmd, str))
        if check and r.returncode != 0:
            raise RuntimeError(f"命令执行失败: {printable}")
        return r


def get_git_count() -> int:
    try:
        r = run(["git", "rev-list", "--count", "HEAD"], capture=True)
        cnt = int((r.stdout or "0").strip())
        return cnt
    except Exception:
        return 0


def write_version_file(version: str):
    (ROOT / "version.txt").write_text(version, encoding="utf-8")
    print(f"版本号已写入: {version}")


def ensure_pyinstaller():
    print_step("检查 PyInstaller")
    try:
        import PyInstaller  # noqa: F401
        print("PyInstaller 已安装")
    except Exception:
        print("未检测到 PyInstaller，正在安装...")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("PyInstaller 安装完成")


def clean_old():
    print_step("清理旧的构建文件")
    for name in ["build", "dist"]:
        p = ROOT / name
        if p.exists():
            shutil.rmtree(p)
            print(f"已删除: {p}")
    for spec in ROOT.glob("*.spec"):
        spec.unlink()
        print(f"已删除: {spec}")


def build_with_pyinstaller():
    print_step("开始打包应用程序")
    cmd = [
        "pyinstaller", "--noconfirm", "--clean",
        "--name", APP_NAME,
        "--icon=res/sscom.ico",
        "--add-data", "res;res",
        "--add-data", "res/sscom.ico;.",
        "--add-data", "version.txt;.",
        "--version-file", "file_version_info.txt",
        "--windowed",
        "--onefile",
        "main.py",
    ]
    run(cmd, cwd=ROOT, check=True)
    print("应用程序打包完成")


def copy_extra_files_to_dist():
    print_step("复制额外资源到 dist\\res")
    dist_res = ROOT / "dist" / "res"
    dist_res.mkdir(parents=True, exist_ok=True)
    src_res = ROOT / "res"
    if src_res.exists():
        # Python 3.8+ 支持 dirs_exist_ok
        for item in src_res.rglob("*"):
            rel = item.relative_to(src_res)
            dest = dist_res / rel
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                shutil.copy2(item, dest)
        print("资源复制完成")
    else:
        print("未找到 res 目录，跳过资源复制")


def find_iscc_path() -> Path:
    default = Path("C:/Program Files (x86)/Inno Setup 6/iscc.exe")
    if default.exists():
        return default
    # 深度搜索 Program Files 路径
    for base in [Path("C:/Program Files (x86)"), Path("C:/Program Files")]:
        for root, _, files in os.walk(base):
            if "iscc.exe" in files:
                return Path(root) / "iscc.exe"
    return None


def resolve_inno_language(iscc_path: Path):
    """根据当前 Inno Setup 安装目录选择可用语言文件。"""
    inno_root = Path(iscc_path).parent
    languages_dir = inno_root / "Languages"
    preferred_patterns = [
        ("chinesesimplified", "ChineseSimplified.isl"),
        ("chinesesimplified", "*Chinese*Simplified*.isl"),
        ("chinesesimplified", "*ChineseSimplified*.isl"),
    ]

    for lang_name, pattern in preferred_patterns:
        if "*" in pattern:
            matches = sorted(languages_dir.glob(pattern))
            if matches:
                return lang_name, matches[0]
        else:
            candidate = languages_dir / pattern
            if candidate.exists():
                return lang_name, candidate

    recursive_matches = sorted(inno_root.rglob("*Chinese*Simplified*.isl"))
    if recursive_matches:
        return "chinesesimplified", recursive_matches[0]

    default_isl = inno_root / "Default.isl"
    if default_isl.exists():
        print("未找到简体中文语言文件，安装包界面将回退为默认语言。")
        return "english", default_isl

    print("未找到 Inno Setup 语言文件，安装包将使用编译器内置默认语言。")
    return None, None


def write_iss_script(version: str, iscc_path: Path) -> Path:
    print_step("生成 Inno Setup 脚本")
    iss_path = ROOT / "installer_script.iss"
    language_name, language_file = resolve_inno_language(iscc_path)
    lines = [
        "; Inno Setup脚本 - 由 oneclick_build.py 自动生成",
        f"#define MyAppName \"{APP_NAME}\"",
        f"#define MyAppVersion \"{version}\"",
        f"#define MyAppPublisher \"{APP_PUBLISHER}\"",
        "#define MyAppURL \"\"",
        f"#define MyAppExeName \"{APP_NAME}.exe\"",
        "",
        "[Setup]",
        "AppId={{" + APP_ID_GUID + "}}",
        "AppName={#MyAppName}",
        "AppVersion={#MyAppVersion}",
        "AppPublisher={#MyAppPublisher}",
        "AppPublisherURL={#MyAppURL}",
        "AppSupportURL={#MyAppURL}",
        "AppUpdatesURL={#MyAppURL}",
        "DefaultDirName={autopf}\\{#MyAppName}",
        "DisableProgramGroupPage=yes",
        "PrivilegesRequiredOverridesAllowed=dialog",
        "OutputDir=installer",
        f"OutputBaseFilename={APP_NAME}_Setup_v{version}",
        "SetupIconFile=res/sscom.ico",
        "Compression=lzma",
        "SolidCompression=yes",
        "WizardStyle=modern",
        "",
        "[Tasks]",
        "Name: \"desktopicon\"; Description: \"{cm:CreateDesktopIcon}\"; GroupDescription: \"{cm:AdditionalIcons}\"; Flags: unchecked",
        "",
        "[Files]",
        "Source: \"dist\\{#MyAppExeName}\"; DestDir: \"{app}\"; Flags: ignoreversion",
        "Source: \"dist\\res\\*\"; DestDir: \"{app}\\res\"; Flags: ignoreversion recursesubdirs createallsubdirs",
        "",
        "[Icons]",
        "Name: \"{autoprograms}\\{#MyAppName}\"; Filename: \"{app}\\{#MyAppExeName}\"",
        "Name: \"{autodesktop}\\{#MyAppName}\"; Filename: \"{app}\\{#MyAppExeName}\"; Tasks: desktopicon",
        "",
        "[Run]",
        "Filename: \"{app}\\{#MyAppExeName}\"; Description: \"{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}\"; Flags: nowait postinstall skipifsilent",
    ]

    if language_name and language_file:
        lang_line = f"Name: \"{language_name}\"; MessagesFile: \"{normalize_windows_path(language_file)}\""
        lines[24:24] = ["[Languages]", lang_line, ""]

    content = "\n".join(lines)
    iss_path.write_text(content, encoding="utf-8")
    print(f"Inno Setup 脚本已生成: {iss_path}")
    return iss_path


def build_installer(iscc: Path, iss_path: Path):
    print_step("使用 Inno Setup 编译安装包")
    installer_dir = ROOT / "installer"
    installer_dir.mkdir(exist_ok=True)
    run([str(iscc), iss_path.name], cwd=ROOT, check=True)
    print("安装包生成完成")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Gavin COM 一键打包安装器")
    parser.add_argument("--dry-run", action="store_true", help="试运行，打印步骤但不实际执行")
    args = parser.parse_args()

    print_step("计算版本号")
    git_count = get_git_count()
    major, minor = 1, 0
    patch_h, patch_l = git_count // 100, git_count % 100
    version = f"{major}.{minor}.{patch_h}.{patch_l}"
    print(f"计算得到版本号: {version} (git提交次数: {git_count})")

    if args.dry_run:
        print("DRY RUN: 将进行以下步骤 -> 写入version.txt、检查/安装PyInstaller、清理、打包、复制res、生成ISS、查找iscc并编译安装包")
        return 0

    write_version_file(version)
    ensure_pyinstaller()
    clean_old()
    build_with_pyinstaller()
    copy_extra_files_to_dist()

    print_step("检测 Inno Setup")
    iscc = find_iscc_path()
    if not iscc:
        print("警告：未检测到 Inno Setup。将仅完成应用程序打包。")
        exe_path = ROOT / "dist" / f"{APP_NAME}.exe"
        print(f"可执行文件位于: {exe_path}")
        return 0

    iss = write_iss_script(version, iscc)
    build_installer(iscc, iss)
    # 清理临时 ISS 脚本
    try:
        iss.unlink()
    except Exception:
        pass
    exe_path = ROOT / "dist" / f"{APP_NAME}.exe"
    setup_glob = list((ROOT / "installer").glob(f"{APP_NAME}_Setup_v{version}.exe"))
    print_step("完成")
    print(f"可执行文件位于: {exe_path}")
    if setup_glob:
        print(f"安装包位于: {setup_glob[0]}")
    else:
        print(f"安装包位于: {ROOT / 'installer'} 下（文件名含版本号）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
