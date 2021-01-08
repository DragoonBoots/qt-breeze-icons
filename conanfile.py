import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from xml.dom import minidom

from conans import CMake, ConanFile, tools


class QtBreezeIconsConan(ConanFile):
    name = 'qt-breeze-icons'
    kde_stable_version = '5.77.0'
    license = 'LGPL-3.0'
    description = 'Conan recipe for using Breeze icons as a Qt icon theme'
    url = 'https://github.com/DragoonBoots/qt-breeze-icons'
    topics = ["Qt"]
    no_copy_source = True
    exports = ('version.txt',)
    options = dict(pattern='ANY')
    default_options = dict(pattern='.+')

    def _get_version(self):
        version_file_path = Path(self.recipe_folder) / 'version.txt'
        if version_file_path.is_file():
            with version_file_path.open(mode='rt') as version_file:
                return version_file.readline().strip()
        else:
            return self.kde_stable_version

    def set_version(self):
        self.version = self._get_version()

    def build_requirements(self):
        self.build_requires("ECM/{}@dragoonboots/stable".format(self._get_version()))

    def source(self):
        # Zip downloads cause corrupted symlinks, so git clone is required
        git = tools.Git()
        git.clone('https://invent.kde.org/frameworks/breeze-icons.git', branch='v{}'.format(self.version), shallow=True)

    def _configure_cmake(self) -> CMake:
        cmake = CMake(self)
        cmake.definitions['ECM_DIR'] = str(Path(self.deps_cpp_info['ECM'].res_paths[0]) / 'ECM' / 'cmake')
        cmake.definitions['BINARY_ICONS_RESOURCE'] = False
        cmake.definitions['SKIP_INSTALL_ICONS'] = True
        cmake.definitions['WITH_ICON_GENERATION'] = False
        # This will create generated icons (e.g. 24x24 versions)
        cmake.configure()
        return cmake

    def _icon_paths(self, path: Path):
        """Iterate through the given directory for requested icon files"""
        paths = set()
        if path.is_dir():
            for child in path.iterdir():
                paths.update(self._icon_paths(child))
        elif path.is_file():
            if path.suffix == '.svg' and re.fullmatch(str(self.options.pattern), path.stem) is not None:
                paths.add(path)
        return paths

    class ProgressBar:
        dots_per_line = 50

        def __init__(self, total: int):
            self.total = total
            self.count = 0
            self._count_width = str(len(str(self.total)))
            self._last_step_time = datetime.now()
            self._average_step_time = None
            self._print_progress()

        def increment(self, count: int = 1):
            this_step_time = datetime.now()
            if self._average_step_time is None:
                self._average_step_time = this_step_time - self._last_step_time
            else:
                self._average_step_time = (this_step_time - self._last_step_time + self._average_step_time) / 2
            self._last_step_time = this_step_time
            for i in range(count):
                self.count += 1
                if self.count % self.dots_per_line == 0:
                    self._print_progress()
                print('.', end='')

        def finish(self):
            if self.count < self.total:
                self.increment(self.total - self.count)
            print()
            print()

        def _print_progress(self):
            # Writes, for example, "0:00:00 remaining:   0/100 "
            if self._average_step_time is None:
                # Extra spaces line it up with time printing
                remaining = '  Unknown time'
            else:
                remaining = self._average_step_time * (self.total - self.count)
            progress = '{remaining} remaining: {count: >{width}}/{total}'.format(
                width=self._count_width, remaining=remaining, count=self.count, total=self.total)
            print(os.linesep + progress, end=' ')

    def build(self):
        cmake = self._configure_cmake()
        cmake.build()

    def package(self):
        # Don't use cmake install to allow for filtering and doctoring the generated QRC
        @dataclass
        class IconTheme:
            name: str
            dir_name: str

        icon_themes = (
            IconTheme(name='breeze-light', dir_name='icons'),
            IconTheme(name='breeze-dark', dir_name='icons-dark'),
        )
        # Hold a list of installed icons for copying and generate the QRC
        root = ET.Element('RCC', {'version': '1.0'})
        qresource = ET.SubElement(root, 'qresource', {'prefix': '/icons'})
        for theme in icon_themes:
            print('Copying {theme}...'.format(theme=theme.name))
            source_icons = Path(self.source_folder) / theme.dir_name
            generated_icons = Path(self.build_folder) / theme.dir_name / 'generated'
            dirs = (source_icons, generated_icons)
            for directory in dirs:
                print('Packaging from {dir}...'.format(dir=directory))
                paths = list(self._icon_paths(directory))
                # Sorting helps keep things neat for potential debugging
                paths.sort()
                progressbar = self.ProgressBar(len(paths))
                for path in paths:
                    # copied is a list of packaged paths
                    copied = self.copy(str(path.relative_to(directory)), src=str(directory),
                                       dst='share/{}'.format(theme.name), symlinks=True)
                    for new_path in copied:
                        rel_path = Path(new_path).relative_to(Path(self.package_folder) / 'share')
                        file = ET.SubElement(qresource, 'file')
                        file.text = str(rel_path)
                    progressbar.increment()
                progressbar.finish()
            # Copy theme file and add to QRC
            for theme_path in self.copy('index.theme', src=str(source_icons), dst='share/{}'.format(theme.name)):
                rel_path = Path(theme_path).relative_to(Path(self.package_folder) / 'share')
                file = ET.SubElement(qresource, 'file')
                file.text = str(rel_path)

        # Generate the QRC
        qrc_file_path = Path(self.build_folder) / 'breeze-icons.qrc'
        out = '<!DOCTYPE RCC>' + os.linesep + ET.tostring(root, encoding='unicode', xml_declaration=False)
        with qrc_file_path.open('wt') as qrc_file:
            qrc_file.write(minidom.parseString(out).toprettyxml())
        self.copy(str(qrc_file_path.relative_to(self.build_folder)), dst='share', keep_path=False)

    def package_info(self):
        self.cpp_info.name = 'BreezeIcons'
        self.cpp_info.resdirs = ["share"]
