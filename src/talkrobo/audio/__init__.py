"""マイク録音・音声再生・相づち。

このパッケージのサブモジュールは sounddevice を import する。
ARM 版 Windows で x64 版 Python を使っていると、そのままでは
DLL の選択を誤って読み込みに失敗するため、先に環境を整えておく。
"""

from ._win_arm import use_process_architecture

use_process_architecture()
