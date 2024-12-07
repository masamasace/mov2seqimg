# to import module from parent directory
import sys, os
from pathlib import Path

cur_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(str(Path(cur_dir).parent))

# import module
import mov2seqimg as m2s

mov_file_path = r"D:\shiga\01_survey_data\2024-10-05_noto\2024-10-05\21_working_dir\GS040002.mp4"
gpx_file_path = r"D:\shiga\01_survey_data\2024-10-05_noto\2024-10-05\21_working_dir\GS040002.gpx"

m2s = m2s.Mov2SeqImg(mov_file_path, gpx_file_path)
m2s.convert(fps=1000)