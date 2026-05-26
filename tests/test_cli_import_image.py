import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wsa.cli import main


class ImportImageCommandTests(unittest.TestCase):
    def test_import_image_ocrs_existing_image_and_saves_it_as_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            image_path = root / "phone-screenshot.png"
            image_path.write_bytes(b"not a real png in this unit test")

            stdout = io.StringIO()
            with (
                patch(
                    "wsa.cli.ocr_image",
                    return_value="王志平\n智能客服项目本周推出还有哪些工作？我还需要提供哪些？",
                ) as mocked_ocr,
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "import-image",
                        str(image_path),
                        "--contact",
                        "王志平",
                    ]
                )

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            mocked_ocr.assert_called_once_with(image_path)
            self.assertIn("inserted capture=", output)
            self.assertIn("contact=王志平", output)
            self.assertIn("signals=项目/合作,问题", output)
            self.assertIn(f"image={image_path}", output)
            with contextlib.closing(sqlite3.connect(db_path)) as conn:
                stored = conn.execute(
                    """
                    select p.name, c.source, c.image_path
                    from captures c
                    join people p on p.id = c.person_id
                    """
                ).fetchone()
            self.assertEqual(("王志平", "image", str(image_path)), stored)

    def test_import_image_accepts_multiple_images_in_one_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            first_image = root / "phone-001.png"
            second_image = root / "phone-002.png"
            first_image.write_bytes(b"first fake screenshot")
            second_image.write_bytes(b"second fake screenshot")

            stdout = io.StringIO()
            with (
                patch(
                    "wsa.cli.ocr_image",
                    side_effect=[
                        "王志平\n智能客服项目本周推出还有哪些工作？",
                        "王志平\n下周方便继续聊聊这个项目吗？",
                    ],
                ) as mocked_ocr,
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "import-image",
                        str(first_image),
                        str(second_image),
                        "--contact",
                        "王志平",
                    ]
                )

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            self.assertEqual([((first_image,),), ((second_image,),)], mocked_ocr.call_args_list)
            self.assertEqual(2, output.count("inserted capture="))
            self.assertIn(f"image={first_image}", output)
            self.assertIn(f"image={second_image}", output)
            self.assertIn("summary images=2 inserted=2 duplicate=0 image_attached=0", output)
            with contextlib.closing(sqlite3.connect(db_path)) as conn:
                stored = conn.execute(
                    """
                    select p.name, c.image_path
                    from captures c
                    join people p on p.id = c.person_id
                    order by c.id
                    """
                ).fetchall()
            self.assertEqual(
                [("王志平", str(first_image)), ("王志平", str(second_image))],
                stored,
            )

    def test_import_image_accepts_directory_and_imports_supported_images_in_name_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            import_dir = root / "phone"
            import_dir.mkdir()
            later_image = import_dir / "IMG_0002.PNG"
            earlier_image = import_dir / "IMG_0001.jpg"
            ignored_file = import_dir / "notes.txt"
            later_image.write_bytes(b"later fake screenshot")
            earlier_image.write_bytes(b"earlier fake screenshot")
            ignored_file.write_text("not a screenshot", encoding="utf-8")

            stdout = io.StringIO()
            with (
                patch(
                    "wsa.cli.ocr_image",
                    side_effect=[
                        "张三\n这个项目我整理了第一版想法。",
                        "张三\n下周方便继续聊聊这个项目吗？",
                    ],
                ) as mocked_ocr,
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "import-image",
                        str(import_dir),
                        "--contact",
                        "张三",
                    ]
                )

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            self.assertEqual([((earlier_image,),), ((later_image,),)], mocked_ocr.call_args_list)
            self.assertEqual(2, output.count("inserted capture="))
            self.assertIn(f"image={earlier_image}", output)
            self.assertIn(f"image={later_image}", output)
            self.assertNotIn("notes.txt", output)
            with contextlib.closing(sqlite3.connect(db_path)) as conn:
                image_paths = [
                    row[0]
                    for row in conn.execute(
                        "select image_path from captures order by id"
                    ).fetchall()
                ]
            self.assertEqual([str(earlier_image), str(later_image)], image_paths)

    def test_import_image_sorts_directory_images_with_numeric_filename_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            import_dir = root / "phone"
            import_dir.mkdir()
            first_image = import_dir / "IMG_2.png"
            second_image = import_dir / "IMG_10.png"
            first_image.write_bytes(b"first fake screenshot")
            second_image.write_bytes(b"second fake screenshot")

            stdout = io.StringIO()
            with (
                patch(
                    "wsa.cli.ocr_image",
                    side_effect=[
                        "张三\n第二张之前的项目截图。",
                        "张三\n第十张后面的项目截图。",
                    ],
                ) as mocked_ocr,
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "import-image",
                        str(import_dir),
                        "--contact",
                        "张三",
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertEqual([((first_image,),), ((second_image,),)], mocked_ocr.call_args_list)

    def test_import_image_explains_when_directory_has_no_supported_images(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            import_dir = root / "phone"
            import_dir.mkdir()
            (import_dir / "notes.txt").write_text("not a screenshot", encoding="utf-8")

            stdout = io.StringIO()
            with (
                patch("wsa.cli.ocr_image") as mocked_ocr,
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "import-image",
                        str(import_dir),
                        "--contact",
                        "张三",
                    ]
                )

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            mocked_ocr.assert_not_called()
            self.assertIn("没有找到可导入的图片", output)
            self.assertIn(str(import_dir), output)
            self.assertIn("png/jpg/jpeg/heic/tif/tiff", output)

    def test_import_image_explains_when_path_does_not_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            missing_image = root / "missing-phone-screenshot.png"

            stdout = io.StringIO()
            with (
                patch("wsa.cli.ocr_image") as mocked_ocr,
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "import-image",
                        str(missing_image),
                        "--contact",
                        "张三",
                    ]
                )

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            mocked_ocr.assert_not_called()
            self.assertIn("找不到图片或目录", output)
            self.assertIn(str(missing_image), output)

    def test_import_image_explains_when_direct_file_is_not_supported_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "social.db"
            text_file = root / "notes.txt"
            text_file.write_text("not a screenshot", encoding="utf-8")

            stdout = io.StringIO()
            with (
                patch("wsa.cli.ocr_image") as mocked_ocr,
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "import-image",
                        str(text_file),
                        "--contact",
                        "张三",
                    ]
                )

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            mocked_ocr.assert_not_called()
            self.assertIn("不支持的图片类型", output)
            self.assertIn(str(text_file), output)
            self.assertIn("png/jpg/jpeg/heic/tif/tiff", output)


if __name__ == "__main__":
    unittest.main()
