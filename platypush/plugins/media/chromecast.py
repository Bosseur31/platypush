import pychromecast

from platypush.plugins import Plugin, action


class MediaChromecastPlugin(Plugin):
    """
    Plugin to interact with Chromecast devices

    Requires:

        * **pychromecast** (``pip install pychromecast``)
    """

    STREAM_TYPE_UNKNOWN = "UNKNOWN"
    STREAM_TYPE_BUFFERED = "BUFFERED"
    STREAM_TYPE_LIVE = "LIVE"

    def __init__(self, chromecast=None, *args, **kwargs):
        """
        :param chromecast: Default Chromecast to cast to if no name is specified
        :type chromecast: str
        """

        super().__init__(*args, **kwargs)

        self.chromecast = chromecast
        self.chromecasts = {}


    @action
    def get_chromecasts(self):
        """
        Get the list of Chromecast devices
        """

        return [ {
            'type': cc.cast_type,
            'name': cc.name,
            'manufacturer': cc.device.manufacturer,
            'model_name': cc.model_name,
            'uuid': str(cc.device.uuid),
            'address': cc.host,
            'port': cc.port,

            'status': ({
                'app': {
                    'id': cc.app_id,
                    'name': cc.app_display_name,
                },

                'is_active_input': cc.status.is_active_input,
                'is_stand_by': cc.status.is_stand_by,
                'is_idle': cc.is_idle,
                'namespaces': cc.status.namespaces,
                'volume': round(100*cc.status.volume_level, 2),
                'muted': cc.status.volume_muted,
            } if cc.status else {}),
        } for cc in pychromecast.get_chromecasts() ]


    def get_chromecast(self, chromecast=None):
        if not chromecast:
            if not self.chromecast:
                raise RuntimeError('No Chromecast specified nor default Chromecast configured')
            chromecast = self.chromecast


        if chromecast not in self.chromecasts:
            self.chromecasts = pychromecast.get_chromecasts()
            cast = next(cc for cc in self.chromecasts
                        if cc.device.friendly_name == chromecast)
        else:
            cast = self.chromecasts[chromecast]

        return cast

    @action
    def cast_media(self, media, content_type, chromecast=None, title=None,
                   image_url=None, autoplay=True, current_time=0,
                   stream_type=STREAM_TYPE_BUFFERED, subtitles=None,
                   subtitles_lang='en-US', subtitles_mime='text/vtt',
                   subtitle_id=1):
        """
        Cast media to a visible Chromecast

        :param media: Media to cast
        :type media: str

        :param content_type: Content type
        :type content_type: str

        :param chromecast: Chromecast to cast to. If none is specified, then the default configured Chromecast will be used.
        :type chromecast: str

        :param title: Optional title
        :type title: str

        :param image_url: URL of the image to use for the thumbnail
        :type image_url: str

        :param autoplay: Set it to false if you don't want the content to start playing immediately (default: true)
        :type autoplay: bool

        :param current_time: Time to start the playback in seconds (default: 0)
        :type current_time: int

        :param stream_type: Type of stream to cast. Can be BUFFERED (default), LIVE or UNKNOWN
        :type stream_type: str

        :param subtitles: URL of the subtitles to be shown
        :type subtitles: str

        :param subtitles_lang: Subtitles language (default: en-US)
        :type subtitles_lang: str

        :param subtitles_mime: Subtitles MIME type (default: text/vtt)
        :type subtitles_mime: str

        :param subtitle_id: ID of the subtitles to be loaded (default: 1)
        :type subtitle_id: int
        """

        cast = self.get_chromecast(chromecast)
        cast.wait()
        mc = cast.media_controller
        mc.namespace = 'urn:x-cast:com.google.cast.sse'

        mc.play_media(media, content_type, title=title, thumb=image_url,
                      current_time=current_time, autoplay=autoplay,
                      stream_type=stream_type, subtitles=subtitles,
                      subtitles_lang=subtitles_lang, subtitles_mime=subtitles_mime,
                      subtitle_id=subtitle_id)

        mc.block_until_active()

    @action
    def disconnect(self, chromecast=None, timeout=None, blocking=True):
        """
        Disconnect a Chromecast and wait for it to terminate

        :param chromecast: Chromecast to cast to. If none is specified, then the default configured Chromecast will be used.
        :type chromecast: str

        :param timeout: Number of seconds to wait for disconnection (default: None: block until termination)
        :type timeout: float

        :param blocking: If set (default), then the code will wait until disconnection, otherwise it will return immediately.
        :type blocking: bool
        """

        cast = self.get_chromecast(chromecast)
        cast.disconnect(timeout=timeout, blocking=blocking)

    @action
    def join(self, chromecast=None, timeout=None, blocking=True):
        """
        Blocks the thread until the Chromecast connection is terminated.

        :param chromecast: Chromecast to cast to. If none is specified, then the default configured Chromecast will be used.
        :type chromecast: str

        :param timeout: Number of seconds to wait for disconnection (default: None: block until termination)
        :type timeout: float

        :param blocking: If set (default), then the code will wait until disconnection, otherwise it will return immediately.
        :type blocking: bool
        """

        cast = self.get_chromecast(chromecast)
        cast.join(timeout=timeout, blocking=blocking)

    @action
    def quit_app(self, chromecast=None):
        """
        Exits the current app on the Chromecast

        :param chromecast: Chromecast to cast to. If none is specified, then the default configured Chromecast will be used.
        :type chromecast: str
        """

        cast = self.get_chromecast(chromecast)
        cast.quit_app()

    @action
    def reboot(self, chromecast=None):
        """
        Reboots the Chromecast

        :param chromecast: Chromecast to cast to. If none is specified, then the default configured Chromecast will be used.
        :type chromecast: str
        """

        cast = self.get_chromecast(chromecast)
        cast.reboot()

    @action
    def set_volume(self, volume, chromecast=None):
        """
        Set the Chromecast volume

        :param volume: Volume to be set, between 0 and 100
        :type volume: float

        :param chromecast: Chromecast to cast to. If none is specified, then the default configured Chromecast will be used.
        :type chromecast: str
        """

        cast = self.get_chromecast(chromecast)
        cast.set_volume(volume/100)

    @action
    def volume_up(self, chromecast=None, delta=10):
        """
        Turn up the Chromecast volume by 10% or delta.

        :param chromecast: Chromecast to cast to. If none is specified, then the default configured Chromecast will be used.
        :type chromecast: str

        :param delta: Volume increment between 0 and 100 (default: 100%)
        :type delta: float
        """

        cast = self.get_chromecast(chromecast)
        delta /= 100
        cast.volume_up(min(delta, 1))


    @action
    def volume_down(self, chromecast=None, delta=10):
        """
        Turn down the Chromecast volume by 10% or delta.

        :param chromecast: Chromecast to cast to. If none is specified, then the default configured Chromecast will be used.
        :type chromecast: str

        :param delta: Volume decrement between 0 and 100 (default: 100%)
        :type delta: float
        """

        cast = self.get_chromecast(chromecast)
        delta /= 100
        cast.volume_down(max(delta, 0))


    @action
    def toggle_mute(self, chromecast=None):
        """
        Toggle the mute status on the Chromecast

        :param chromecast: Chromecast to cast to. If none is specified, then the default configured Chromecast will be used.
        :type chromecast: str
        """

        cast = self.get_chromecast(chromecast)
        cast.set_volume_muted(not cast.status.volume_muted)


# vim:sw=4:ts=4:et:

