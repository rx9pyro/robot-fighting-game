from setuptools import setup

setup(
    name="SteelArena",
    options={
        'build_apps': {
            'gui_apps': {
                'SteelArena': 'main.py',  # Твой главный файл (переименованный говно.py)
            },
            'include_patterns': [
                '**/*.png',
                '**/*.jpg',
                '**/*.bam',
                '**/*.egg',
                '**/*.prc',
                '**/*.wav',
                '**/*.mp3',
            ],
            'plugins': [
                'pandagl',
                'p3openal_audio',
            ],
            'platforms': [
                'win_amd64',
            ],
            'log_filename': '$USER_APPDATA/SteelArena/output.log', # Пишет лог, если игра упадет
            'log_append': False,
        }
    }
)