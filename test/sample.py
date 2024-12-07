# to import module from parent directory
import sys, os
from pathlib import Path

cur_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(str(Path(cur_dir).parent))

# import module
import mov2seqimg as m2s

# 変数 (movファイルのパス, gpxファイルのパス, fps)
########### この下の3つの変数を変更してください。########### 

## mov_file_path: 動画ファイルのパスです
mov_file_path = r"PATH_TO_MOV_FILE"

## gpx_file_path: GPXファイルのパスです
gpx_file_path = r"PATH_TO_GPX_FILE"

## fps: 画像を切り出す間隔です。10であれば、1秒間に10枚の画像を切り出します。
##      ※ もともとの動画のfpsとは異なります。
##      ※ もともとの動画のfpsよりも大きい値を設定した場合は、もともとの動画のfpsで画像を切り出します。
##         つまり、もともとの動画のfpsが30で、fpsが1000を設定した場合、1秒間に30枚の画像を切り出します。
fps = 1000

########### ここから下は変更しないでください。########### 

m2s = m2s.Mov2SeqImg(mov_file_path, gpx_file_path)
m2s.convert(fps=fps)