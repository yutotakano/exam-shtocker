# Ignore these exam hashes as they are known bad or duplicates.
known_bad_hashes: list[bytes] = [
    # IADS May 2024 - There was a better copy provided by the professor and it was manually uploaded
    bytes.fromhex("024607a87ae1691d0e92486ec5ee844949109ab93fbecfb680a8980ea59eab4e"),
    # Computer Security December 2023 - Level 11 version is identical to UG version
    bytes.fromhex("b4a342506676f77aca96d5585fbde572799be567abeaaed18332b172c4a888e1"),
]
