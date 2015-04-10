from wand._cffi import get_libraries


def test_smoke_test_library():
    c, wand, magick = get_libraries()
    assert wand.MagickWandGenesis() == None
    assert wand.MagickWandTerminus() == None


def test_read_core_image():
    c, wand, magick = get_libraries()
    wand.MagickWandGenesis()

    class WAND(object):
        def __init__(self, filename=None):
            self._id_ = wand.NewMagickWand()
            if filename:
                ok = wand.MagickReadImage(self._id_, filename.encode())
                if not ok:
                    raise ValueError('Not able to read ' + repr(filename))
        def __del__(self):
            self._id_ = wand.DestroyMagickWand(self._id_)

        def __repr__(self):
            w = wand.MagickGetImageWidth(self._id_)
            h = wand.MagickGetImageHeight(self._id_)
            return '<WAND {0}x{1}>'.format(w, h)

    assert repr(WAND(filename='rose:')) == '<WAND 70x46>'
    wand.MagickWandTerminus()


def test_create_canvas():
    c, wand, magick = get_libraries()
    wand.MagickWandGenesis()

    image = wand.NewMagickWand()
    color = wand.NewPixelWand()
    assert image
    assert color
    if not wand.PixelSetColor(color, b'orange'):
        raise Exception('Unable to site pixel color')
    if not wand.MagickSetSize(image, 8, 8):
        raise Exception('Unable to site size')
    if not wand.MagickSetBackgroundColor(image, color):
        raise Exception('Unable to set image color')

    iterator = wand.NewPixelIterator(image)
    width = c.cast('size_t', 0)
    pixels = wand.PixelGetNextIteratorRow(iterator, c.addressof(width))
    #assert width[0] == 8
    #assert pixels[0] == pixels[7]

    #iterator = wand.DestroyPixelIterator(iterator)

    #color = wand.DestroyPixelWand(color)
    #image = wand.DestroyMagickWand(image)
    #wand.MagickWandTerminus()