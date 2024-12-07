from pathlib import Path
import ffmpeg
from datetime import datetime as dt
import gpxpy
import pandas as pd
import numpy as np
import piexif
import scipy.interpolate as spi
import matplotlib.pyplot as plt

def latlon_to_rational(latlon):
    latlon = abs(latlon)
    deg = int(latlon)
    min = int((latlon - deg) * 60)
    sec = int(((latlon - deg) * 60 - min) * 60 * 100000)
    return [(deg, 1), (min, 1), (sec, 100000)]

def ele_to_rational(ele):
    ele = int(ele * 1000)
    return (ele, 1000)

class Mov2SeqImg:

    def __init__(self, mov_file_path, 
                 gpx_file_path, 
                 seq_image_dir = None):

        
        self.mov_file_path = Path(mov_file_path).resolve()
        self.gpx_file_path = Path(gpx_file_path).resolve()

        if seq_image_dir is None:
            self.seq_image_dir = self.mov_file_path.parent / 'res'
        else:
            self.seq_image_dir = Path(seq_image_dir).resolve()

        print("----------------------------------")
        self._create_seq_image_dir()
        self._load_mov()
        self._load_gpx()
        print("----------------------------------")

        
    def _create_seq_image_dir(self):

        if not self.seq_image_dir.exists():
            self.seq_image_dir.mkdir(parents = True)
            print("Created directory: ", self.seq_image_dir)
        else:
            print("Directory already exists: ", self.seq_image_dir)
        
        
    def _load_mov(self):
        
        mov_info = ffmpeg.probe(str(self.mov_file_path))

        self.total_frames = int(mov_info['streams'][0]['nb_frames'])
        self.total_duration = float(mov_info['format']['duration'])
        self.fps = float(mov_info['streams'][0]['r_frame_rate'].split('/')[0]) / float(mov_info['streams'][0]['r_frame_rate'].split('/')[1])
        
        self.creation_time = mov_info['format']["tags"]["creation_time"]
        self.creation_time = dt.strptime(self.creation_time, "%Y-%m-%dT%H:%M:%S.%f%z")

        print("Loaded mov file: ", self.mov_file_path)
        print(" total frames: ", self.total_frames)
        print(" total duration: ", self.total_duration)
        print(" frames/duration: ", self.total_frames / self.total_duration)
        print(" fps: ", self.fps)

    def _load_gpx(self):

        gps_data = gpxpy.parse(self.gpx_file_path.open())

        # create pandas dataframe with abs time, rel time, lat, lon, ele
        data = []
        for track in gps_data.tracks:
            for segment in track.segments:
                for point in segment.points:
                    data.append([point.time, point.time - gps_data.tracks[0].segments[0].points[0].time, point.latitude, point.longitude, point.elevation])
        
        self.gps_data = pd.DataFrame(data, columns=["abs_time", "rel_time", "lat", "lon", "ele"])

        print("Loaded gpx file: ", self.gpx_file_path)
        print(" Number of track points: ", len(self.gps_data))
        print(" Duration: ", self.gps_data.iloc[-1]['rel_time'].total_seconds())

    def convert(self, 
                start_time = None, 
                end_time = None, 
                time_interval = None, 
                fps = None, debug = False):
        """
        convert mov file to sequence images.

        Parameters
        ----------
        start_time : float, optional
            start time in seconds. The default is None, which means convert from the beginning.
        end_time : float, optional
            end time in seconds. The default is None, which means convert until the end.
        time_interval : float
            time interval in seconds. The default is 1.
        fps : float, optional
            frames per second. The default is 1.
            if time_interval is None, fps must be set.
            if fps exceeds the original fps, the original fps is used.
        """
        self._set_params(start_time, end_time, time_interval, fps)
        print("----------------------------------")
        self._get_frame_list()
        print("----------------------------------")
        self._merge_gnss2frame_list()
        if debug:
            self._debug_merged_frame_list()
        print("----------------------------------")
        self._extract_images()


    def _set_params(self, start_time, end_time, time_interval, clip_fps):
        if start_time is None:
            self.start_time = 0
        else:
            self.start_time = start_time
        
        if end_time is None:
            self.end_time = self.total_duration
        else:
            self.end_time = end_time
        
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time.")
        
        if time_interval is None:
            if clip_fps is not None:
                if clip_fps > self.fps:
                    clip_fps = self.fps
                self.time_interval = 1 / clip_fps
                self.clip_fps = clip_fps
            else:
                raise ValueError("Either time_interval or fps must be set.")
        else:
            clip_fps = 1 / time_interval

            if clip_fps > self.fps:
                clip_fps = self.fps
                time_interval = 1 / clip_fps
                        
            self.time_interval = time_interval
            self.clip_fps = clip_fps
        
        print("Set parameters:")
        print(" start time: ", self.start_time)
        print(" end time: ", self.end_time)
        print(" time interval: ", self.time_interval)
        print(" clip fps: ", self.clip_fps)
        

    def _get_frame_list(self):

        start_frame = self.start_time * self.fps
        end_frame = self.end_time * self.fps

        frame_num_list = np.arange(start_frame, end_frame, self.fps / self.clip_fps)
        frame_num_list = np.clip(frame_num_list, 0, self.total_frames - 1)
        frame_num_list = np.int64(frame_num_list)

        frame_time_stamp = pd.to_timedelta(frame_num_list / self.fps, unit = 's')

        self.frame_list = pd.DataFrame({"frame_num": frame_num_list, "time_stamp": frame_time_stamp})

        print("Frame list:")
        print(" start frame: ", self.frame_list["frame_num"].iloc[0])
        print(" end frame: ", self.frame_list["frame_num"].iloc[-1])
        print(" number of frames: ", len(self.frame_list))

    
    def _merge_gnss2frame_list(self):

        # INFO: try to use absolute time instead of relative time
        # but even considering the difference due to the time zone, 
        # there is still a unknown time difference between the two data (mov and gpx)
        # so, I will use relative time for now.

        # compare self.total_duration and self.gps_data["rel_time"].iloc[-1]
        if abs(self.total_duration - self.gps_data["rel_time"].iloc[-1].total_seconds()) > 1:

            print("WARNING: The difference between the duration of the mov file and the gpx file is more than 1 second.")
            print("         The last frame of the mov file may not be synchronized with the last track point of the gpx file.")


        # apply second-order spline interpolation to the gps data

        self.lat_interp = spi.interp1d(self.gps_data["rel_time"].dt.total_seconds(), self.gps_data["lat"], kind = 'quadratic', fill_value = 'extrapolate')
        self.lon_interp = spi.interp1d(self.gps_data["rel_time"].dt.total_seconds(), self.gps_data["lon"], kind = 'quadratic', fill_value = 'extrapolate')
        self.ele_interp = spi.interp1d(self.gps_data["rel_time"].dt.total_seconds(), self.gps_data["ele"], kind = 'quadratic', fill_value = 'extrapolate')

        self.merged_frame_list = self.frame_list.copy()

        self.merged_frame_list["lat"] = self.lat_interp(self.merged_frame_list["time_stamp"].dt.total_seconds())
        self.merged_frame_list["lon"] = self.lon_interp(self.merged_frame_list["time_stamp"].dt.total_seconds())
        self.merged_frame_list["ele"] = self.ele_interp(self.merged_frame_list["time_stamp"].dt.total_seconds())

        self.merged_frame_list = self.merged_frame_list.astype({"frame_num": int})
        self.merged_frame_list = self.merged_frame_list[["frame_num", "time_stamp", "lat", "lon", "ele"]]

    def _debug_merged_frame_list(self):

        fig, ax = plt.subplots(3, 1, figsize = (10, 10))

        ax[0].plot(self.gps_data["rel_time"].dt.total_seconds(), self.gps_data["lat"], label = "lat", marker = 'o', linestyle = '')
        ax[0].plot(self.merged_frame_list["time_stamp"].dt.total_seconds(), self.merged_frame_list["lat"], label = "lat_interp", marker = 'x', linestyle = '')
        ax[0].set_xlabel("time (s)")
        ax[0].set_ylabel("latitude")
        ax[0].legend()

        ax[1].plot(self.gps_data["rel_time"].dt.total_seconds(), self.gps_data["lon"], label = "lon", marker = 'o', linestyle = '')
        ax[1].plot(self.merged_frame_list["time_stamp"].dt.total_seconds(), self.merged_frame_list["lon"], label = "lon_interp", marker = 'x', linestyle = '')
        ax[1].set_xlabel("time (s)")
        ax[1].set_ylabel("longitude")
        ax[1].legend()

        ax[2].plot(self.gps_data["rel_time"].dt.total_seconds(), self.gps_data["ele"], label = "ele", marker = 'o', linestyle = '')
        ax[2].plot(self.merged_frame_list["time_stamp"].dt.total_seconds(), self.merged_frame_list["ele"], label = "ele_interp", marker = 'x', linestyle = '')
        ax[2].set_xlabel("time (s)")
        ax[2].set_ylabel("elevation")
        ax[2].legend()

        plt.show()
    
    def _extract_images(self):

        for i, row in self.merged_frame_list.iterrows():
            frame_num = int(row["frame_num"])
            lat = row["lat"]
            lon = row["lon"]
            ele = row["ele"]

            img_file_path = self.seq_image_dir / f"{self.mov_file_path.stem}_{frame_num:06d}.jpeg"

            (ffmpeg
             .input(str(self.mov_file_path), ss = frame_num / self.fps)
             .output(str(img_file_path), vframes = 1, qmin = 1, qmax = 1, q = 1)
             .run(overwrite_output = True, quiet = True))

            exif = piexif.load(str(img_file_path))

            exif["GPS"][piexif.GPSIFD.GPSLatitude] = latlon_to_rational(lat)
            exif["GPS"][piexif.GPSIFD.GPSLatitudeRef] = 'N' if lat >= 0 else 'S'
            exif["GPS"][piexif.GPSIFD.GPSLongitude] = latlon_to_rational(lon)
            exif["GPS"][piexif.GPSIFD.GPSLongitudeRef] = 'E' if lon >= 0 else 'W'
            exif["GPS"][piexif.GPSIFD.GPSAltitude] = ele_to_rational(ele)
            
            piexif.insert(piexif.dump(exif), str(img_file_path))

            print(f"Extracted image: {img_file_path.stem}.jpeg")


            