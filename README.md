Movie Track Analyzer
====================
This script scans a specified directory for movie files and analyzes their audio tracks, providing detailed information such as language, format, channels, bitrate, title, and size. It offers various filtering options to display desired results. You can also choose to delete unwanted audio tracks to save storage space.

Requirements
------------

To install the dependencies, use the following command:

`pip install -r requirements.txt`

The required packages are:

*   requests
*   prettytable
*   tmdbv3api
*   tqdm
*   pycountry

Usage
-----
The script requires Python 3 and depends on the ffprobe and ffmpeg executables. To use the script, save it as a Python file (e.g., movie\_track\_analyzer.py) and run it from the command line with the required arguments. For example:

bash

```bash
python movie_track_analyzer.py -d /path/to/your/movie/directory -ff /path/to/ffmpeg-folder
```

This will scan the specified directory for movie files and display information about their audio tracks in a table.

Some of the optional arguments include:

*   `-se` or `--show-errors`: Show error messages for files that could not be scanned
*   `-tn` or `--track-number`: Show only movies with an audio track count greater than or equal to the number provided
*   `-nu` or `--no-unknown`: Hide movies with unknown language tracks
*   `-ou` or `--only-unknown`: Show only movies with unknown language tracks
*   `-fo` or `--foreign-only`: Show only movies with foreign language tracks
*   `-es` or `--exclude-same`: Exclude files where the tracks are all the same language
*   `-os` or `--only-same`: Display only files where the tracks are all the same language
*   `-no` or `--no-output`: Do not display the output and go directly to prompting the user for file deletion
*   `-nd` or `--no-delete`: Do not prompt the user for deletion after displaying the output
*   `-w` or `--work`: Enable TMDB\_pull\_language
*   `-wl` or `--wrong-language`: Show files with wrong language tracks (only works with `-w`)

After displaying the audio track information, you can choose to delete specific audio tracks to save storage space.

The `-w` or `--work` flag enables the use of the `TMDB_pull_language` function in the script. This function retrieves the original language of the movie from The Movie Database (TMDb) API. To use this flag, you'll need to have a valid TMDb API key and add it to the script. This feature can be helpful to compare the original language of the movie with the languages of the audio tracks provided in the file.

The `-wl` or `--wrong-language` flag is used in conjunction with the `-w` flag. When both flags are enabled, the script will display only those movie files with audio tracks in languages different from the original language of the movie as retrieved from TMDb. This can help you identify files with incorrect or additional language tracks that you may want to remove or modify.

Keep in mind that to use the `-wl` flag, you must also enable the `-w` flag, as the `-wl` flag relies on the TMDb API to determine the original language of the movie.

Note on size and bitrate accuracy
---------------------------------

The size and bitrate values displayed in the output table are calculated based on the metadata provided by the media files. These values might not always be accurate, as they can be affected by factors such as variable bitrates, container overhead, or incorrect metadata. While the script provides a useful overview of the audio tracks, it's important to keep this limitation in mind when making decisions based on the size and bitrate values.
