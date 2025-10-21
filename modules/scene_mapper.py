import re, random
from collections import defaultdict

from modules.model_song import Song

BASE_GENRE_PATTERNS = {
    r"metal|grind|doom|sludge|thrash|black|death|heavy|viking|metalcore|post hardcore": "metal",
    r"hip[- ]?hop|rap|trap|grime": "rap",
    r"synthwave|dark wave|new wave|synthpop|darkwave|synth rock|post punk|goth|gothic": "gothic",
    r"rock|punk|grunge|garage|emo|indie rock|psychedelia|alternative": "rock",
    r"electropop|industrial|ebm|neue deutsche härte|shock rock|gothic rock|aggrotech": "industrial",
    r"pop|hyperpop|k[- ]?pop|charts|wochen|weeks|dance": "pop",
    r"techno|house|trance|idm|edm|dnb|d b|drum and bass|dubstep": "electronic",
    r"classical|baroque|symphony|concerto|romantic": "classical",
    r"jazz|swing|bebop|fusion|big band": "jazz",
    r"blues|soul|funk|r&b|r b|rnb|rhythm and blues": "blues",
    r"folk|country|americana|bluegrass": "folk",
    r"reggae|ska|dub": "reggae",
    r"ambient|drone|new age|soundscape": "ambient",
    r"world|afro|latin|balkan|ethno|tango": "world",
    r"soundtrack|ost|score|filme|videospiele|filmmusik": "soundtrack",
}

SONG_SCENE_MAP = {}

def map_genre(subgenres: list[str]) -> str:
    genres = {}
    n_max = 0
    best_match = "other"
    for subgenre in subgenres:
        s = subgenre.strip().lower()
        for pattern, main_genre in BASE_GENRE_PATTERNS.items():
            if re.search(pattern, s):
                n = genres.get(main_genre, 0) + 1
                genres[main_genre] = n
                if n > n_max:
                    best_match, n_max = main_genre, n
    return best_match


def sample_songs_by_scene(songs: list[Song], n: int) -> dict[str, list[Song]]:
    scene_to_songs = defaultdict(list)

    for song in songs:
        if not hasattr(song, "genres") or not hasattr(song, "popularity"):
            continue
        if not song.hash in SONG_SCENE_MAP:
            scene = map_genre(song.genres)
            SONG_SCENE_MAP[song.hash] = scene
        else:
            scene = SONG_SCENE_MAP.get(song.hash, "other")
        scene_to_songs[scene].append(song)

    result = {}
    for scene, group in scene_to_songs.items():
        if not group:
            result[scene] = []
            continue

        unique_group = list(set(group))
        result[scene] = []

        for _ in range(min(n, len(unique_group))):
            weights = [max(s.popularity, 0.01) for s in unique_group]
            sampled = random.choices(unique_group, weights=weights, k=1)[0]
            result[scene].append(sampled)
            unique_group.remove(sampled)
                

    for key, value in result.items():
        print(f"Found {len(value)} songs for {key}")

    scene_dict_serialized = {
        scene: [song.to_simple_dict() for song in songs]
        for scene, songs in result.items() if len(songs) >= n
    }

    return scene_dict_serialized