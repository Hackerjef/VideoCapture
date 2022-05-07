import gevent.threading
from gevent import monkey

monkey.patch_all()
import gevent.event
import sys
import time

import numpy as np
import pygame
import pygame.camera
import pygame.time
import pygame_menu
import sounddevice as sd

pygame.init()
pygame.camera.init(None)
pygame.display.set_caption("Capture")
pygame.transform.set_smoothscale_backend("MMX")


class AudioThread(gevent.threading.Thread):
    def __init__(self, *args, **kwargs):
        super(AudioThread, self).__init__(*args, **kwargs)
        self.running = True
        self.audio_out = None
        self.audio_in = None
        self.stream = None

        self.wait = gevent.event.Event()
        self.multiplier = 0.10
        self.mute = False

    def AudioCallback(self, indata, outdata, frames, time, status: sd.CallbackFlags):  # noqa
        if self.mute:
            outdata[:] = indata * 0
            return
        outdata[:] = indata * self.multiplier

    def run(self):
        import sounddevice as sdi
        while self.running:
            try:
                if self.audio_out is not None and self.audio_in is not None:
                    devicein = sdi.query_devices(self.audio_in)
                    self.stream = sdi.Stream(device=(self.audio_in, self.audio_out), samplerate=48000, blocksize=4096,
                                             channels=devicein['max_input_channels'], callback=self.AudioCallback,
                                             latency=0)
                    self.stream.start()
                    self.wait.wait(timeout=None)
                else:
                    print("Audio device not set.. Waiting")
                    self.wait.wait(timeout=None)
            except Exception as e:  # noqa
                self.audio_in = None
                self.audio_out = None
                print(e)
            if self.running:
                self.wait._flag = False

    def restart(self):
        print("Restarting Audio..")
        self.stream.stop()
        self.wait.set()

    def end(self):
        print("Shuting down Audio..")
        self.running = False
        self.mute = True
        if self.stream:
            self.stream.stop()
        self.wait.set()

    def set_audio_devices(self, audio_in, audio_out, restart=True):
        self.audio_in = audio_in
        self.audio_out = audio_out
        if restart:
            self.restart()

    def set_volume(self, vol):
        if vol < 0 > 1:
            raise ValueError("Volume too high or low :)")
        self.multiplier = vol


RES = (1920, 1017)


class Game:
    def __init__(self):
        # CONFIG VALUES
        # TODO: Make config class, :)
        self.video_device: str = "USB Video"
        self.audio_device_in: int = 2
        self.audio_device_out: int = 9

        # Devices setup
        self.menu: pygame_menu.Menu = None  # noqa
        self.video = None
        self.audio = AudioThread()
        self.audio.set_audio_devices(self.audio_device_in, self.audio_device_out, False)
        self.audio.start()
        self.video = pygame.camera.Camera(self.video_device, RES)
        self.video.start()
        self.screen_size = RES

        # game setup
        self.running = True
        self.screen = pygame.display.set_mode(RES, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.frameTimer = time.time() + 0.015
        self.fps_over_time = []
        self.setup_menu()

        # menu hold
        self.menu_hold = None

    def grayscale(self, img):
        arr = pygame.surfarray.array3d(img)
        # luminosity filter
        mean_arr = np.mean(arr, axis=2)
        mean_arr3d = mean_arr[..., np.newaxis]
        new_arr = np.repeat(mean_arr3d[:, :, :], 3, axis=2)
        return pygame.surfarray.make_surface(new_arr)

    def get_image(self):
        try:
            return self.video.get_image()
        except:
            return None

    def MenuBG(self):
        if self.video:
            if not self.menu_hold:
                self.menu_hold = self.get_image()
            if self.menu_hold:
                self.screen.blit(self.grayscale(self.menu_hold), (0, 0))
            else:
                self.screen.fill((0, 0, 0))
        else:
            self.screen.fill((0, 0, 0))

    def loop(self):
        while self.running:
            if time.time() >= self.frameTimer or self.menu.is_enabled():
                self.frameTimer = time.time() + 0.015
                if self.video:
                    idata = self.get_image()
                    if idata:
                        self.screen.blit(self.aspect_scale(idata), (0,0))
                    else:
                        self.screen.fill((0, 0, 0))
                else:
                    self.screen.fill((0, 0, 0))

            for event in pygame.event.get():
                if self.menu.is_enabled():
                    if self.menu.update([event]):
                        continue
                match event.type:
                    case pygame.QUIT:
                        self.shutdown()
                    case pygame.KEYDOWN:
                        self.on_keypress(event)
                    case pygame.VIDEORESIZE:
                        self.screen_size = event.dict['size']
                        print(event.dict['size'])
                    case _:
                        continue
            if self.menu.is_enabled():
                self.menu.mainloop(self.screen, bgfun=self.MenuBG)
            else:
                if self.menu_hold:
                    self.menu_hold = None

            pygame.display.update()
            self.fps_over_time.append(self.clock.get_fps())
            self.clock.tick()
            # print(self.clock.get_fps())

    def aspect_scale(self, img):
        bx, by = self.screen_size
        ix, iy = img.get_size()
        if ix > iy:
            # fit to width
            scale_factor = bx / float(ix)
            sy = scale_factor * iy
            if sy > by:
                scale_factor = by / float(iy)
                sx = scale_factor * ix
                sy = by
            else:
                sx = bx
        else:
            # fit to height
            scale_factor = by / float(iy)
            sx = scale_factor * ix
            if sx > bx:
                scale_factor = bx / float(ix)
                sx = bx
                sy = scale_factor * iy
            else:
                sy = by

        return pygame.transform.smoothscale(img, (sx, sy))

    def on_keypress(self, event):
        match event.key:
            case pygame.K_ESCAPE:
                return self.menu.enable()
            case _:
                pass

    def on_VolumeMute(self, option):
        self.audio.mute = option

    def on_VolumeChange(self, val):
        val /= 10
        self.audio.set_volume(val)

    def on_VideoChange(self, args, *kwargs):
        if self.video:
            self.video.stop()
            self.video = None
        self.video = pygame.camera.Camera(args[0][0], RES)
        self.video_device = args[0][0]
        self.video.start()

    def on_AudioOutChange(self, args, *kwargs):
        self.audio_device_out = args[0][1]
        self.audio.set_audio_devices(audio_in=self.audio_device_in, audio_out=self.audio_device_out, restart=True)

    def on_AudioInChange(self, args, *kwargs):
        self.audio_device_in = args[0][1]
        self.audio.set_audio_devices(audio_in=self.audio_device_in, audio_out=self.audio_device_out, restart=True)

    def get_video_devices(self):  # noqa
        vtup = []
        for vid, video in enumerate(pygame.camera.list_cameras()):
            vtup.append((video, vid))
        return vtup

    def get_audio_devices(self, atype="all"):  # noqa
        atup = []
        devices = sd.query_devices()
        for aid, device in enumerate(devices):
            if device['name'] in (
                    "Microphone ()", "Output ()", "Microsoft Sound Mapper", "Primary Sound Capture Driver"):
                continue
            # if '(' in device['name'] and ')' not in device['name']:
            # continue
            if device.get(f'max_{atype}_channels', 0) > 0 or atype == "all":
                atup.append((device['name'], aid))
        return atup

    def setup_menu(self):
        self.menu = pygame_menu.Menu('Settings', 852, 480, theme=pygame_menu.themes.THEME_BLUE, enabled=False,
                                     onclose=pygame_menu.events.CLOSE)
        self.menu.add.dropselect("Audo In", items=self.get_audio_devices('input'), onchange=self.on_AudioInChange,
                                 dropselect_id='audioin_drop', placeholder_add_to_selection_box=False)
        self.menu.add.dropselect("Audo Out", items=self.get_audio_devices('output'), onchange=self.on_AudioOutChange,
                                 dropselect_id='audioout_drop', placeholder_add_to_selection_box=False)
        self.menu.add.dropselect("Video In", items=self.get_video_devices(), onchange=self.on_VideoChange,
                                 dropselect_id='video_drop', placeholder_add_to_selection_box=False)
        self.menu.add.toggle_switch("Mute", default=self.audio.mute, onchange=self.on_VolumeMute)
        self.menu.add.range_slider("volume", default=self.audio.multiplier * 10, increment=1,
                                   onchange=self.on_VolumeChange, range_values=(0, 10))
        self.menu.add.button('Restart audio', self.audio.restart)
        self.menu.add.button('Exit', self.shutdown)

    def shutdown(self):
        if self.menu.is_enabled():
            self.menu.disable()
        self.running = False
        self.audio.end()
        if self.video:
            self.video.stop()
        pygame.camera.quit()
        print(f"Average: {round(np.average(self.fps_over_time), 2)}")


if __name__ == '__main__':
    print("Starting application :)")
    game = Game()
    try:
        game.loop()
    except SystemExit:
        pass
    except KeyboardInterrupt:
        pass
    game.shutdown()
    pygame.quit()
    sys.exit()
