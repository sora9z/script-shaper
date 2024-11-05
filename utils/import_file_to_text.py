from utils.file_reader_list import read_file


def import_file_to_text(selected_file_path):
    try:
        if selected_file_path:
            text_data = read_file(selected_file_path)
            print(f"Importing file: {selected_file_path}")
            return text_data
        else:
            print("No file selected")
            return None
    except Exception as e:
        print(f"Error in import_file_to_text: {e}")
        raise e
