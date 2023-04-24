#!/usr/bin/env python3

# Standard library imports
import os
import json
import fnmatch
import subprocess
import argparse
import re

# Third-party imports
import pycountry
from tqdm import tqdm
from prettytable import PrettyTable
from tmdbv3api import TMDb, Configuration, Movie

def get_movie_files(path, extensions):
    print(f"Scanning directory for movie files: {path}")
    movie_files = []
    for root, dirnames, filenames in os.walk(path):
        for extension in extensions:
            for filename in fnmatch.filter(filenames, f'*.{extension}'):
                movie_files.append(os.path.join(root, filename))

    print(f"Found {len(movie_files)} movie files.")
    return movie_files

def get_audio_track_info(args):
    movie_files = args['movie_files']
    ffmpeg_folder = args['ffmpeg_folder']
    show_errors = args['show_errors']
    exclude_same = args['exclude_same']
    only_same = args['only_same']
    track_number = args['track_number']
    no_unknown = args['no_unknown']
    only_unknown = args['only_unknown']
    foreign_only = args['foreign_only']
    work = args['work']
    wrong_language = args['wrong_language']

    audio_tracks = []
    errors = []

    for movie_file in tqdm(movie_files, desc="Processing files"):
        try:
            ffprobe_path = os.path.join(ffmpeg_folder, 'ffprobe')
            info = json.loads(subprocess.check_output([ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_streams', '-show_format', movie_file]))
            filename = movie_file
            file_ext = os.path.splitext(filename)[1]
            audio_streams = [stream for stream in info['streams'] if stream['codec_type'] == 'audio']
            file_duration = float(info['format']['duration'])
            if foreign_only:
                has_eng_track = any([stream for stream in audio_streams if stream.get('tags', {}).get('language', '') == 'eng'])
                if has_eng_track:
                    continue

            if track_number is None or len(audio_streams) >= track_number:
                has_eng_track = any(stream.get('tags', {}).get('language', '').lower() == 'eng' for stream in audio_streams)
                has_another_language = any(stream.get('tags', {}).get('language', '').lower() not in ['unknown', 'eng'] for stream in audio_streams)
                all_same_language = len(set([stream.get('tags', {}).get('language', '').lower() for stream in audio_streams])) == 1

                if exclude_same and all_same_language:
                    continue
                if only_same and not all_same_language:
                    continue

                if not foreign_only or (not has_eng_track and has_another_language):
                    for idx, audio_stream in enumerate(audio_streams):
                        language = audio_stream.get('tags', {}).get('language', 'unknown')
                        title = audio_stream.get('tags', {}).get('title', '')

                        if no_unknown and language.lower() == 'unknown':
                            continue
                        if only_unknown and language.lower() != 'unknown':
                            continue

                        codec_name = audio_stream['codec_name']
                        channels = audio_stream['channels']
                        sample_rate = int(audio_stream['sample_rate'])

                        if 'bit_rate' in audio_stream:
                            bitrate = int(audio_stream['bit_rate'])
                            bitrate_str = f"{bitrate // 1000} Kbps"
                        elif codec_name.lower() == 'aac':
                            bitrate = channels * sample_rate
                            bitrate_str = f"~{bitrate // 1000} Kbps"
                        else:
                            bitrate = None
                            bitrate_str = 'N/A'

                        title = title[:40]

                        if bitrate:
                            track_size = (bitrate * file_duration) / (8 * 1024 * 1024)  # in MB
                            track_size_str = f"{track_size:.2f} MB"
                        else:
                            track_size_str = "N/A"

                        audio_track = {
                            'File': filename,
                            'FullFilePath': movie_file,
                            'Track': audio_stream['index'],
                            'Language': language,
                            'Format': codec_name,
                            'Channels': channels,
                            'Bitrate': bitrate_str,
                            'Title': title,
                            'Size': track_size_str
                        }
                        audio_tracks.append(audio_track)
        except Exception as e:
            errors.append(f"Error processing {movie_file}: {str(e)}")

    if show_errors:
        for error in errors:
            print(error)
    if work:
        TMDB_pull_language(audio_tracks, ffmpeg_folder, wrong_language)

    return audio_tracks, errors

def test_api_key(tmdb, api_key):
    tmdb.api_key = api_key
    config = Configuration()
    try:
        config.info()
        return True
    except Exception as e:
        return False

def extract_movie_id(file_name):
    imdb_pattern = r"{imdb-(tt\d+)}"
    tmdb_pattern = r"{tmdb-(\d+)}"

    imdb_match = re.search(imdb_pattern, file_name)
    tmdb_match = re.search(tmdb_pattern, file_name)

    if imdb_match:
        return "imdb", imdb_match.group(1)
    elif tmdb_match:
        return "tmdb", tmdb_match.group(1)
    else:
        return None, None

def convert_iso_639_1_to_639_3(iso_639_1):
    try:
        language = pycountry.languages.get(alpha_2=iso_639_1)
        if language.alpha_3 == 'zho':
            return 'chi'
        return language.alpha_3
    except AttributeError:
        return None

def get_original_language(tmdb, source, movie_id):
    tmdb_movie = Movie()
    if source == "imdb":
        movie = tmdb_movie.external(external_id=movie_id, external_source="imdb_id")
        if movie and movie.get("movie_results"):
            tmdb_id = movie["movie_results"][0]["id"]
            movie = tmdb_movie.details(tmdb_id)
        else:
            return None
    else:
        movie = tmdb_movie.details(movie_id)
    original_language_iso_639_1 = getattr(movie, 'original_language', None)
    return convert_iso_639_1_to_639_3(original_language_iso_639_1)

def tmdb_delete_track(movie_data_list, audio_tracks, ffmpeg_folder):
    total_space_saved = 0
    file_summary = []

    for movie_data in movie_data_list:
        file_name = movie_data["File"]
        original_language = movie_data["original_language"]
        tracks_to_delete = []
        tracks_to_keep = []

        # Filter audio_tracks for the current file
        file_audio_tracks = [track for track in audio_tracks if track["File"] == movie_data["FullFilePath"]]

        for track in file_audio_tracks:
            if track["Language"] != original_language:
                tracks_to_delete.append(f"{track['Track']}({track['Language']})")
            else:
                tracks_to_keep.append(f"{track['Track']}({track['Language']})")

        # Only append the summary if there are tracks to keep
        if tracks_to_keep:
            file_summary.append({
                "file_name": file_name,
                "original_language": original_language,
                "tracks_to_delete": tracks_to_delete,
                "tracks_to_keep": tracks_to_keep
            })

    for i, summary in enumerate(file_summary, 1):
        print(f"\n{i}. {summary['file_name']}:")
        print(f"\tOriginal_Language: {summary['original_language']}")
        print(f"\tTracks to delete: {', '.join(summary['tracks_to_delete'])}")
        print(f"\tTracks to Keep: {', '.join(summary['tracks_to_keep'])}")

    action = input("\nProceed with the suggested modifications?(Y/N or provide the line numbers to skip): ")

    if action.lower() == 'n':
        print("No modifications made. Exiting.")
        return

    skipped_files = set(map(int, action.split())) if action.lower() != 'y' else set()

    for i, summary in enumerate(file_summary, 1):
        if i not in skipped_files:
            print(f"\nApplying modifications to {summary['file_name']}")

            # Filter audio_tracks for the current file
            file_audio_tracks = [track for track in audio_tracks if os.path.basename(track["File"]) == summary['file_name']]

            input_file_path = file_audio_tracks[0]['FullFilePath']
            temp_output_file_path = os.path.splitext(input_file_path)[0] + "_temp" + os.path.splitext(input_file_path)[1]

            map_options = " ".join(f"-map -0:a:{int(track.split('(')[0]) - 1}" for track in summary['tracks_to_delete'])
            ffmpeg_path = os.path.join(ffmpeg_folder, 'ffmpeg')
            ffmpeg_command = f'"{ffmpeg_path}" -i "{input_file_path}" -map 0 {map_options} -c copy "{temp_output_file_path}"'

            print("Deleting specified tracks...")
            print("Executing command:", ffmpeg_command)

            process = subprocess.run(ffmpeg_command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            initial_size = os.path.getsize(input_file_path)
            final_size = os.path.getsize(temp_output_file_path)
            space_saved = initial_size - final_size
            total_space_saved += space_saved
            print(f"Deleted tracks successfully. Space saved: {space_saved / 1024 / 1024:.2f} MB")


            #Replace the original file with the temp file (if the process was successful)
            if process.returncode == 0:
                os.remove(input_file_path)
                os.rename(temp_output_file_path, input_file_path)
            else:
                print(f"An error occurred while processing {summary['file_name']}. Skipping this file.")
                os.remove(temp_output_file_path)

        else:
            print(f"\nSkipping modifications for {summary['file_name']}")
    print(f"Total space saved: {total_space_saved / 1024 / 1024:.2f} MB")
    print(f"Done. Exiting.")
    
def TMDB_pull_language(audio_tracks, ffmpeg_folder, wrong_language=False):
    print("\nThis feature only works if your files contain either '{imdb-imdbID}' or '{tmdb-tmdbID}' within the file names.")
    while True:
        proceed = input("Do you want to proceed? (y/n): ").lower()
        if proceed in ('y', 'n'):
            break
        print("Invalid input. Please enter 'y' or 'n'.")
    if proceed == 'n':
        print("Aborted by user.")
        return False

    tmdb = TMDb()
    api_key = input("Please enter your TheMovieDatabase API Key: ").strip()
    while not test_api_key(tmdb, api_key):
        print("Error: Invalid API key or failed to connect to TheMovieDatabase.")
        retry = input("Do you want to try again? (y/n): ").lower()
        if retry == 'n':
            print("Aborted by user.")
            return False
        api_key = input("Please enter your TheMovieDatabase API Key: ").strip()

    processed_files = set()
    movie_data_list = []
    for file_info in audio_tracks:
        file_name = file_info["File"]

        # Skip processing if the file has already been processed
        if file_name in processed_files:
            continue
        processed_files.add(file_name)

        source, movie_id = extract_movie_id(file_name)
        
        if source is None or movie_id is None:
            print(f"Skipping file {os.path.basename(file_name)} as it doesn't conform to the standard.")
            continue

        movie_data = {
            "FullFilePath": file_name,
            "File": os.path.basename(file_name),
            "movie_id": movie_id
        }
        movie_data_list.append(movie_data)

    tmdb_movie = Movie()  # Create the tmdb_movie object outside the loop

    for movie_data in tqdm(movie_data_list, desc="Fetching original languages"):
        source, movie_id = extract_movie_id(movie_data["File"])
        if source and movie_id:
            movie_data["original_language"] = get_original_language(tmdb, source, movie_id)
    if wrong_language:
        wrong_language_movies = []
        for movie_data in movie_data_list:
            file_name = movie_data["File"]
            original_language = movie_data["original_language"]
            wrong_language_tracks = []

            file_audio_tracks = [track for track in audio_tracks if track["File"] == movie_data["FullFilePath"]]

            for track in file_audio_tracks:
                if track["Language"] != original_language:
                    wrong_language_tracks.append(f"{track['Track']}({track['Language']})")

            if wrong_language_tracks:
                wrong_language_movies.append({
                    "file_name": file_name,
                    "original_language": original_language,
                    "wrong_language_tracks": wrong_language_tracks
                })

        if wrong_language_movies:
            print("\nFiles with wrong language tracks:")
            for movie in wrong_language_movies:
                print(f"{movie['file_name']} (Original: {movie['original_language']})")
                print(f"Wrong language tracks: {', '.join(movie['wrong_language_tracks'])}\n")
        else:
            print("No files with wrong language tracks were found.")
        return
   
    tmdb_delete_track(movie_data_list, audio_tracks, ffmpeg_folder)
    return True
    
def print_audio_track_table(audio_tracks):
    table = PrettyTable()
    table.field_names = ["File", "Track", "Language", "Format", "Channels", "Bitrate", "Title", "Size"]
    table.align["File"] = "l"
    table.align["Title"] = "l"

    # Group audio tracks by file
    audio_tracks_by_file = {}
    for audio_track in audio_tracks:
        file_key = audio_track['FullFilePath']
        if file_key not in audio_tracks_by_file:
            audio_tracks_by_file[file_key] = []
        audio_tracks_by_file[file_key].append(audio_track)

    # Add a new line and separator row to the table for each unique file
    for file_idx, (file_key, file_audio_tracks) in enumerate(audio_tracks_by_file.items()):
        if file_idx > 0:
            table.add_row(["-" * 75, "", "", "", "", "", "", ""])

        for idx, audio_track in enumerate(file_audio_tracks):
            file_name = os.path.basename(audio_track['FullFilePath'])
            file_ext = os.path.splitext(file_name)[1]
            max_length = 70

            if len(file_name) > max_length:
                file_name = file_name[:max_length - len(file_ext) - 3] + '[...]' + file_ext

            audio_track['File'] = file_name
            values = [audio_track[key] for key in table.field_names]  # Only include values that match table field names
            if idx != 0:
                values[0] = ''  # Remove the file name for all but the first row

            table.add_row(values)

    print(table)

def delete_tracks_from_files(audio_tracks, path, ffmpeg_folder):
    total_space_saved = 0
    for idx, (file_key, file_audio_tracks) in enumerate(audio_tracks.items()):
        while True:
            table = PrettyTable()
            table.field_names = ["File", "Track", "Language", "Format", "Channels", "Bitrate", "Title", "Size"]
            table.align["File"] = "l"

            for audio_track in file_audio_tracks:
                file_name = os.path.basename(audio_track['FullFilePath'])
                file_ext = os.path.splitext(file_name)[1]
                max_length = 70

                if len(file_name) > max_length:
                    file_name = file_name[:max_length - len(file_ext) - 3] + '[...]' + file_ext

                audio_track['File'] = file_name
                values = [audio_track[key] for key in table.field_names]
                table.add_row(values)

            print(table)

            valid_tracks = [audio_track["Track"] for audio_track in file_audio_tracks]
            tracks_to_delete = input("Tracks to delete (space-separated, e.g. 1 3 - enter s to skip this file): ").split()

            if all(track.isdigit() and int(track) in valid_tracks for track in tracks_to_delete) or 's' in tracks_to_delete:
                break
            else:
                print("Invalid input. Please enter valid track numbers or 's' to skip.")

        if 's' in tracks_to_delete:
            print("File will be skipped.")
            continue

        input_file_path = file_audio_tracks[0]['FullFilePath']
        temp_output_file_path = os.path.splitext(input_file_path)[0] + "_temp" + os.path.splitext(input_file_path)[1]

        map_options = " ".join(f"-map -0:a:{int(track) - 1}" for track in tracks_to_delete)
        ffmpeg_path = os.path.join(ffmpeg_folder, 'ffmpeg')
        ffmpeg_command = f'"{ffmpeg_path}" -i "{input_file_path}" -map 0 {map_options} -c copy "{temp_output_file_path}"'

        print("Deleting specified tracks...")
        print("Executing command:", ffmpeg_command)

        process = subprocess.run(ffmpeg_command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        initial_size = os.path.getsize(input_file_path)
        final_size = os.path.getsize(temp_output_file_path)
        space_saved = initial_size - final_size
        total_space_saved += space_saved

        print(f"Deleted tracks successfully. Space saved: {space_saved / 1024 / 1024:.2f} MB")

        # Overwrite the original file with the modified one
        os.remove(input_file_path)
        os.rename(temp_output_file_path, input_file_path)

        # If there are no more files, break the loop
        if idx == len(audio_tracks) - 1:
            break
        else:
            proceed = input("Proceed to the next file? (Y/N): ").lower()
            if proceed == 'n':
                break
    print(f"Total space saved: {total_space_saved / 1024 / 1024:.2f} MB")

def main():
    parser = argparse.ArgumentParser(
        description=("A script that scans a specified directory "
                     "for movie files and analyzes their audio tracks, providing "
                     "detailed information including language, format, channels, "
                     "bitrate, title, and size. Offers various filtering options "
                     "to display desired results."))
    parser.add_argument('-d', '--directory', required=True, help="Directory to scan for movie files")
    parser.add_argument('-se', '--show-errors', action='store_true', help="Show error messages for files that could not be scanned")
    parser.add_argument('-tn', '--track-number', type=int, help="Show only movies where the count of audio tracks is greater than or equal to the number provided")
    parser.add_argument('-nu', '--no-unknown', action='store_true', help="Hide movies with unknown language tracks")
    parser.add_argument('-ou', '--only-unknown', action='store_true', help="Show only movies with unknown language tracks")
    parser.add_argument('-fo', '--foreign-only', action='store_true', help="Show only movies with foreign language tracks")
    parser.add_argument('-es', '--exclude-same', action='store_true', help="Exclude files where the tracks are all the same language")
    parser.add_argument('-os', '--only-same', action='store_true', help="Display only files where the tracks are all the same language")
    parser.add_argument('-no', '--no-output', action='store_true', help="Do not display the output and go directly to prompting the user for file deletion")
    parser.add_argument('-nd', '--no-delete', action='store_true', help="Do not prompt the user for deletion after displaying the output")
    parser.add_argument('-ff', '--ffmpeg-folder', required=True, help="Path to the folder containing ffprobe and ffmpeg executables")
    parser.add_argument('-w', '--work', action='store_true', help="Enable TMDB_pull_language")
    parser.add_argument('-wl', '--wrong-language', action='store_true', help="Show files with wrong language tracks (only works with -w)")
    args = parser.parse_args()

    movie_extensions = ('mkv', 'mp4', 'avi', 'mov', 'wmv', 'flv', 'm4v','m2ts', 'iso')
    movie_files = get_movie_files(args.directory, movie_extensions)
    audio_track_args = {
        'movie_files': movie_files,
        'ffmpeg_folder': args.ffmpeg_folder,
        'show_errors': args.show_errors,
        'exclude_same': args.exclude_same,
        'only_same': args.only_same,
        'track_number': args.track_number,
        'no_unknown': args.no_unknown,
        'only_unknown': args.only_unknown,
        'foreign_only': args.foreign_only,
        'wrong_language': args.wrong_language,
        'work': args.work
    }
    audio_tracks, errors = get_audio_track_info(audio_track_args)
    
    if not args.work:
        if not args.no_output:
            print_audio_track_table(audio_tracks)
            if args.show_errors and errors:
                print("\nErrors encountered during processing:")
                for error in errors:
                    print(error)

        if args.no_delete:
            if args.no_output:
                print("Why would you do this?")
            return

        while True:
            delete_tracks = input("Do you want to proceed with deleting tracks? (Y/N): ")
            if delete_tracks.lower() in ('y', 'n'):
                break
            else:
                print("Invalid input. Please enter either Y or N.")

        if delete_tracks.lower() == 'y':
            audio_tracks_by_file = {}
            for audio_track in audio_tracks:
                file_key = audio_track['File']
                if file_key not in audio_tracks_by_file:
                    audio_tracks_by_file[file_key] = []
                audio_tracks_by_file[file_key].append(audio_track)
            delete_tracks_from_files(audio_tracks_by_file, args.directory, args.ffmpeg_folder)

if __name__ == "__main__":
    main()
