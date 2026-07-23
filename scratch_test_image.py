import sys
from textual.app import App, ComposeResult
from textual.widgets import Static

class ImageApp(App):
    def compose(self) -> ComposeResult:
        from term_image.image import from_file
        # Create a small dummy image
        from PIL import Image
        img = Image.new('RGB', (100, 100), color = 'red')
        img.save('dummy.png')
        
        image = from_file('dummy.png')
        yield Static(str(image))

if __name__ == "__main__":
    ImageApp().run()
