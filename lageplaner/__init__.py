def classFactory(iface):
    from .lageplaner_plugin import LageplanerPlugin

    return LageplanerPlugin(iface)
