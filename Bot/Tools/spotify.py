import spotipy
from spotipy.oauth2 import SpotifyOAuth
import Tools.login as login

# Documentation
"""
This script allows basic control of Spotify playback using the Spotipy library.
It supports actions such as playing a track, pausing, skipping to the next track, and adjusting volume.

Setup:
1. Install Spotipy using `pip install spotipy`.
2. Set up a Spotify Developer account and create an application.
3. Replace 'YOUR_CLIENT_ID', 'YOUR_CLIENT_SECRET', and 'YOUR_REDIRECT_URI' with your actual credentials.

Usage:
- Run the script and use the provided functions to control Spotify playback.
"""

# Set up authentication
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=str(login.spotify_login()[1]),
    client_secret=str(login.spotify_login()[0]),
    redirect_uri="http://localhost:8080",
    scope="user-library-read,user-read-playback-state,user-modify-playback-state"
))

# Function to play a track by its Spotify URI
def play_track(track_uri):
    sp.start_playback(uris=[track_uri])

def play_liked_songs():
    # Get the user's saved tracks (Liked Songs)
    results = sp.current_user_saved_tracks()
    
    # Extract the track URIs
    track_uris = [item['track']['uri'] for item in results['items']]
    
    # Start playback of the liked songs
    if track_uris:
        sp.start_playback(uris=track_uris)
    else:
        print("No liked songs found.")

# Function to pause playback
def pause():
    playback_info = sp.current_playback()
    if playback_info and playback_info['is_playing']:
        sp.pause_playback()
        print("Playback paused.")
    else:
        print("No song is currently playing.")

# Function to resume playback
def resume():
    playback_info = sp.current_playback()
    if playback_info and not playback_info['is_playing']:
        sp.start_playback()
        print("Playback resumed.")
    else:
        print("Song is already playing or no active device found.")

# Function to skip to the next track
def skip():
    sp.next_track()

# Function to set volume (0 to 100)
def volume_up(volume):
    sp.volume(volume)


        

# Example usage
if __name__ == "__main__":
    print("Spotify Control Program")
    action = input("Enter action (play, pause, skip, volume, resume): ").strip().lower()

    if action == "play":
        track_uri = input("Enter Spotify track URI: ").strip()
        play_track(track_uri)
        playing = True

    elif action == "pause":
        pause()
        playing = False

    elif action == "skip":
        skip()

    elif action == "volume up":
        volume = int(input("Enter volume level (0-100): ").strip())
        #set_volume(volume)
    elif action == "resume":
        resume()
    else:
        print("Invalid action")

def action(question):
    if "play my liked songs" in question.lower():
        play_liked_songs()
    elif "loop" in question.lower():
        pass
    elif "pause" in question.lower():
        pause()
    elif "skip" in question.lower():
        skip()
    elif "resume" in question.lower():
        resume()
    elif "volume up" in question.lower():
        sp.volume(min(sp.current_playback()['device']['volume_percent'] + 10, 100))
    elif "volume down" in question.lower():
        sp.volume(min(sp.current_playback()['device']['volume_percent'] - 10, 0))