import os
import re
import threading

from platypush.context import get_bus, get_plugin
from platypush.plugins.media import PlayerState, MediaPlugin
from platypush.message.event.media import MediaPlayEvent, MediaPlayRequestEvent, \
    MediaPauseEvent, MediaStopEvent, MediaSeekEvent, MediaVolumeChangedEvent, \
    MediaMuteChangedEvent, NewPlayingMediaEvent

from platypush.plugins import action


class MediaVlcPlugin(MediaPlugin):
    """
    Plugin to control vlc instances

    Requires:

        * **python-vlc** (``pip install python-vlc``)
        * **vlc** executable on your system
    """

    _default_vlc_args = []

    def __init__(self, args=None, *argv, **kwargs):
        """
        Create the vlc wrapper.

        :param args: Default arguments that will be passed to the vlc executable
            as a list. See `vlc --help` for available options.
        :type args: list[str]
        """

        super().__init__(*argv, **kwargs)

        self.args = self._default_vlc_args
        if args:
            self.args.update(args)

        self._player = None
        self._playback_rebounce_event = threading.Event()
        self._latest_seek = None
        self._on_stop_callbacks = []


    @classmethod
    def _watched_event_types(cls):
        import vlc
        return [getattr(vlc.EventType, evt) for evt in [
            'MediaPlayerLengthChanged', 'MediaPlayerMediaChanged',
            'MediaDurationChanged', 'MediaPlayerMuted',
            'MediaPlayerUnmuted', 'MediaPlayerOpening', 'MediaPlayerPaused',
            'MediaPlayerPlaying', 'MediaPlayerPositionChanged',
            'MediaPlayerStopped', 'MediaPlayerTimeChanged', 'MediaStateChanged',
            'MediaPlayerForward', 'MediaPlayerBackward',
            'MediaPlayerEndReached', 'MediaPlayerTitleChanged',
            'MediaPlayerAudioVolume',
        ] if hasattr(vlc.EventType, evt)]

    def _init_vlc(self, resource, *args):
        import vlc

        if self._player:
            self._player.stop()
            self._player = None

        vlc_args = self.args.copy()
        if args:
            vlc_args.update(args)

        for k,v in self._env.items():
            os.environ[k] = v

        self._player = vlc.MediaPlayer(resource, *vlc_args)

        for evt in self._watched_event_types():
            self._player.event_manager().event_attach(
                eventtype=evt, callback=self._event_callback())

    def _event_callback(self):
        def callback(event):
            from vlc import EventType
            self.logger.debug('Received vlc event: {}'.format(event))
            bus = get_bus()

            if event.type == EventType.MediaPlayerPlaying:
                bus.post(MediaPlayEvent(resource=self._get_current_resource()))
            elif event.type == EventType.MediaPlayerPaused:
                bus.post(MediaPauseEvent())
            elif event.type == EventType.MediaPlayerStopped or \
                event.type == EventType.MediaPlayerEndReached:
                bus.post(MediaStopEvent())
                if self._player:
                    self._player = None
                self._latest_seek = None
                for callback in self._on_stop_callbacks:
                    callback()
            elif event.type == EventType.MediaPlayerTitleChanged:
                bus.post(NewPlayingMediaEvent(resource=event.u.new_title))
            elif event.type == EventType.MediaPlayerMediaChanged:
                bus.post(NewPlayingMediaEvent(resource=event.u.filename))
            elif event.type == EventType.MediaPlayerLengthChanged:
                bus.post(NewPlayingMediaEvent(resource=self._get_current_resource()))
            elif event.type == EventType.MediaPlayerTimeChanged:
                pos = float(event.u.new_time/1000)
                if self._latest_seek is None or \
                        abs(pos-self._latest_seek) > 5:
                    bus.post(MediaSeekEvent(position=pos))
                self._latest_seek = pos
            elif event.type == EventType.MediaPlayerAudioVolume:
                bus.post(MediaVolumeChangedEvent(volume=self._player.audio_get_volume()))
            elif event.type == EventType.MediaPlayerMuted:
                bus.post(MediaMuteChangedEvent(mute=True))
            elif event.type == EventType.MediaPlayerUnmuted:
                bus.post(MediaMuteChangedEvent(mute=False))

        return callback


    @action
    def play(self, resource, subtitles=None, *args):
        """
        Play a resource.

        :param resource: Resource to play - can be a local file or a remote URL
        :type resource: str

        :param subtitles: Path to optional subtitle file
        :type subtitles: str

        :param args: Extra runtime arguments that will be passed to the
            vlc executable as a list
        :type args: list[str]
        """

        get_bus().post(MediaPlayRequestEvent(resource=resource))
        resource = self._get_resource(resource)

        if resource.startswith('file://'):
            resource = resource[len('file://'):]
        elif resource.startswith('magnet:?'):
            self._is_playing_torrent = True
            return get_plugin('media.webtorrent').play(resource)

        self._init_vlc(resource, *args)
        if subtitles:
            if subtitles.startswith('file://'):
                subtitles = subtitles[len('file://'):]
            self._player.set_subtitle_file(subtitles)

        self._is_playing_torrent = False
        self._player.play()
        return self.status()


    @action
    def pause(self):
        """ Toggle the paused state """
        if not self._player:
            return (None, 'No vlc instance is running')
        if not self._player.can_pause():
            return (None, 'The specified media type cannot be paused')

        self._player.pause()
        return self.status()

    @action
    def quit(self):
        """ Quit the player (same as `stop`) """
        self._stop_torrent()
        if not self._player:
            return (None, 'No vlc instance is running')

        # XXX the .stop() call hangs for some reason
        self._player.stop()
        self._player.release()
        return { 'state': PlayerState.STOP.value }

    @action
    def stop(self):
        """ Stop the application (same as `quit`) """
        return self.quit()

    @action
    def voldown(self, step=10.0):
        """ Volume down by (default: 10)% """
        if not self._player:
            return (None, 'No vlc instance is running')
        return self.set_volume(self._player.audio_get_volume()-step)

    @action
    def volup(self, step=10.0):
        """ Volume up by (default: 10)% """
        if not self._player:
            return (None, 'No vlc instance is running')
        return self.set_volume(self._player.audio_get_volume()+step)

    @action
    def set_volume(self, volume):
        """
        Set the volume

        :param volume: Volume value between 0 and 100
        :type volume: float
        """
        if not self._player:
            return (None, 'No vlc instance is running')

        volume = max(0, min(100, volume))
        self._player.audio_set_volume(volume)
        return { 'volume': volume }

    @action
    def seek(self, position):
        """
        Seek backward/forward by the specified number of seconds

        :param relative_position: Number of seconds relative to the current cursor
        :type relative_position: int
        """
        if not self._player:
            return (None, 'No vlc instance is running')
        if not self._player.is_seekable():
            return (None, 'The resource is not seekable')

        media = self._player.get_media()
        if not media:
            return (None, 'No media loaded')

        pos = min(media.get_duration()/1000, max(0, position))
        self._player.set_time(int(pos*1000))
        return { 'position': pos }

    @action
    def back(self, offset=60.0):
        """ Back by (default: 60) seconds """
        if not self._player:
            return (None, 'No vlc instance is running')

        media = self._player.get_media()
        if not media:
            return (None, 'No media loaded')

        pos = max(0, (self._player.get_time()/1000)-offset)
        return self.seek(pos)

    @action
    def forward(self, offset=60.0):
        """ Forward by (default: 60) seconds """
        if not self._player:
            return (None, 'No vlc instance is running')

        media = self._player.get_media()
        if not media:
            return (None, 'No media loaded')

        pos = min(media.get_duration()/1000, (self._player.get_time()/1000)+offset)
        return self.seek(pos)

    @action
    def toggle_subtitles(self, visibile=None):
        """ Toggle the subtitles visibility """
        if not self._player:
            return (None, 'No vlc instance is running')

        if self._player.video_get_spu_count() == 0:
            return (None, 'The media file has no subtitles set')

        if self._player.video_get_spu() is None or \
                self._player.video_get_spu() == -1:
            self._player.video_set_spu(0)
        else:
            self._player.video_set_spu(-1)

    @action
    def toggle_fullscreen(self):
        """ Toggle the fullscreen mode """
        if not self._player:
            return (None, 'No vlc instance is running')
        self._player.toggle_fullscreen()

    @action
    def set_subtitles(self, filename):
        """ Sets media subtitles from filename """
        if not self._player:
            return (None, 'No vlc instance is running')
        if filename.startswith('file://'):
            filename = filename[len('file://'):]

        self._player.video_set_subtitle_file(filename)

    @action
    def remove_subtitles(self):
        """ Removes (hides) the subtitles """
        if not self._player:
            return (None, 'No vlc instance is running')
        self._player.video_set_spu(-1)

    @action
    def is_playing(self):
        """
        :returns: True if it's playing, False otherwise
        """
        if not self._player:
            return False
        return self._player.is_playing()

    @action
    def load(self, resource, **args):
        """
        Load/queue a resource/video to the player
        """
        if not self._player:
            return self.play(resource, **args)
        return self._player.set_media(resource)

    @action
    def mute(self):
        """ Toggle mute state """
        if not self._player:
            return (None, 'No vlc instance is running')
        self._player.audio_toggle_mute()

    @action
    def set_position(self, position):
        """
        Seek backward/forward to the specified absolute position (same as ``seek``)
        """
        return self.seek(position)

    @action
    def status(self):
        """
        Get the current player state.

        :returns: A dictionary containing the current state.

        Example::

            output = {
                "filename": "filename or stream URL",
                "state": "play"  # or "stop" or "pause"
            }
        """
        import vlc
        if not self._player:
            return { 'state': PlayerState.STOP.value }

        vlc_state = self._player.get_state()
        state = PlayerState.STOP.value
        filename = self._player.get_media().get_mrl() \
            if self._player.get_media() else None

        if vlc_state == vlc.State.Playing:
            state = PlayerState.PLAY.value
        if vlc_state == vlc.State.Paused:
            state = PlayerState.PAUSE.value

        time = float(self._player.get_time()/1000) if self._player.get_time() \
            is not None else None

        media = self._player.get_media()
        duration = media.get_duration()/1000 if media and media.get_duration() \
            is not None else None

        return {
            'filename': filename,
            'state': state,
            'time': time,
            'duration': duration,
        }

    def on_stop(self, callback):
        self._on_stop_callbacks.append(callback)

    def _get_current_resource(self):
        if not self._player or not self._player.get_media():
            return
        return self._player.get_media().get_mrl()


# vim:sw=4:ts=4:et:
