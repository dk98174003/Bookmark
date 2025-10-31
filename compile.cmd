cd C:\Python\bookmark
pyinstaller --icon=it4home.ico --add-data "it4home.ico;." bookmark.py -n Bookmark --onefile --noconfirm --noconsole --windowed
del bookmark.spec
rmdir /S /Q build
copy dist\*.exe .
rmdir /S /Q dist

