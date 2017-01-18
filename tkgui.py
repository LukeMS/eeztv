
from array import array
import logging
import os
import string
import threading

os.environ["TCL_LIBRARY"] = (
    os.path.join(os.path.dirname(__file__), "tcl8.6")
)

os.environ["TK_LIBRARY"] = (
    os.path.join(os.path.dirname(__file__), "tk8.6")
)

import tkinter as tk
from tkinter import *
from tkinter import ttk
from tkinter.ttk import *
from tkinter import messagebox
from _tkinter import TclError

import eztvit
from PIL.ImageTk import PhotoImage
import umsgpack
import singleton

from msgpack_storage import MessagePackStorage, Show
from queries import Query
from tooltip import set_tooltip

# will sys.exit(-1) if other instance is running
lock = singleton.SingleInstance()


class EZTVScrapper(Tk):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.iconbitmap('ui/eztv.ico')
        self.title("EZTV Scrapper")

        # hide the main window during time we insert widgets
        # self.withdraw()

        self.grid()

        self.create_log_box()

        self.logger.info("loading database...")
        self.db = MessagePackStorage('tiny.bz2msgpack')

        self.load_favorites()

        self.create_select_frame()
        self.create_separator(row=1)
        self.create_toolbar()
        self.create_progress_bar()
        self.grid_columnconfigure(0, weight=1)

        self.update_lock = threading.Lock()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.printable = array('I', sorted(map(ord, string.printable)))

        # restore the window
        # self.deiconify()

        self.logger.ipinfo("ready")

    def search_window(self):
        SearchWindow(self)

    def fav_window(self):
         FavWindow(self)

    def search_name(self, event):
        c = event.char
        n = ord(c)
        if n in self.printable:
            for name in self.names:
                if name.lower().startswith(c.lower()):
                    self.menu_name_var.set(name)
                    return

    def create_progress_bar(self):
        self.progress = Progressbar(self, orient="horizontal",
                                    length=200, mode="determinate")
        self.progress.grid(column=0, row=5, sticky=E + W, columnspan=4)

        self.progress_0 = 0
        self.progress_1 = 0

    def read_progress(self, v=None):
        '''simulate reading 500 bytes; update progress bar'''
        if v:
            self.progress_0 += v
        self.progress["value"] = self.progress_0

    def on_close(self):
        if not messagebox.askokcancel("Quit", "Do you want to quit?"):
            return
        if self.update_lock.locked() and not messagebox.askokcancel(
                "Quit", "Update is still running. Quit anyway?"):
            return
        self.db.close()
        self.save_favorites()
        sys.exit()

    def load_favorites(self):
        try:
            with open("fav.msgpack", "rb") as f:
                self.favorites = umsgpack.loads(f.read())
        except FileNotFoundError:
            self.favorites = []

    def save_favorites(self):
        with open("fav.msgpack", "wb") as f:
            f.write(umsgpack.dumps(self.favorites))

    def create_log_box(self):
        self.log_box = tk.Text(self, background="black", state="disabled")
        self.log_box.grid(column=0, row=4, sticky=E + W + N + S, columnspan=4)
        self.grid_rowconfigure(4, weight=1)

        # setup logging handlers using the Tk instance created above
        # the pattern below can be used in other threads...
        # ...to allow other thread to send msgs to the gui
        # in this example, we set up two handlers just for demonstration (you
        # could add a fileHandler, etc)

        self.logger = logging.getLogger()

        # stderrHandler = logging.StreamHandler()  # no arguments => stderr
        # EzLogger.addHandler(stderrHandler)

        gui_handler = LogHandler(self.log_box)
        self.logger.addHandler(gui_handler)
        self.logger.setLevel(logging.INFO)

    def update_gui(self, name=None):
        self._names = None
        self.reset_menu_name(name)
        self.change_name(self.current_name)

    def update_database(self):
        if not self.update_lock.locked() and messagebox.askyesno(
            "Get all new shows",
            (
                "This will get all the new show names currently not in the "
                "database. It could take a long time. Proceed?"
            )
        ):
            self.abort_update = False

            shows = self.available_shows
            down_shows = set(self.names)
            new_shows = sorted(set(shows.keys()).difference(down_shows))
            self.progress["value"] = 0
            self.progress_1 = len(new_shows)
            self.progress["maximum"] = self.progress_1

            self.update_thread = threading.Thread(
                target=self._update_database, daemon=True)
            self.update_thread.start()
        elif messagebox.askokcancel(
                "Interrupt update",
                "Update is still running. Interrupt it?"
        ):
            self.abort_update = True

    @property
    def ez(self):
        if getattr(self, "_ez", None) is None:
            self._ez = eztvit.EztvIt()
        return self._ez

    @property
    def available_shows(self):
        if getattr(self, "_available_shows", None) is None:
            self._available_shows = {
                v: k for (k, v) in self.ez.get_shows().items()}
        return self._available_shows

    def update_show(self, _id=None, name=None):
        if _id is None:
            name = self.current_name
            _id = self.available_shows[self.current_name]
            update = True
        else:
            update = False

        episodes = self.ez.get_episodes_by_id(_id)
        self.logger.ipinfo(
            """checking "%s"'s episodes...""" % name)
        self._dbfy(episodes, _id, name)

        if update:
            self.update_gui(name=self.current_name)

    def _update_database(self):
        info = self.logger.info
        self.update_lock.acquire()
        self.up_all_button.config(state="running")
        shows = self.available_shows
        down_shows = set(self.names)
        info("shows in database: %.2d" % len(down_shows))
        new_shows = sorted(set(shows.keys()).difference(down_shows))
        info("shows NOT in database: %.2d" % len(new_shows))

        if len(new_shows):
            info("updating database...")
            self.logger.warning("do not close the program during update")
            for name in new_shows:
                if not self.abort_update:
                    _id = shows[name]
                    self.update_show(_id, name)
                    self.read_progress(1)

            if not self.abort_update:
                info("done updating database")
            else:
                self.logger.error("update interrupted by the user")
            self.update_gui()
            self.logger.warning(
                "It is safe to quit now (or get some torrents!)")

        else:
            self.logger.ipinfo("no new shows available, you are up-to-date")

        self.update_lock.release()
        self.up_all_button.config(state="normal")

    def _dbfy(self, data, _id, name):
        db = self.db
        if not data:
            blank = Show(name=name, id=_id)
            db.insert(blank)
        for season_k, season_v in data.items():
            for ep_k, l in season_v.items():
                for ep_v in l:
                    release = ep_v['release']
                    magnet = ep_v['download'].get('magnet', None)
                    torrents = ep_v['download'].get('torrents', None)
                    torrents = torrents[0] if torrents else torrents
                    size_mb = ep_v['size_mb']
                    show = Show(
                        name=name, id=_id,
                        season=int(season_k), episode=int(ep_k),
                        release=release,
                        magnet=magnet,
                        torrents=torrents,
                        size_mb=size_mb
                    )
                    if show not in self.db.cache:
                        self.logger.info("Adding: %s" % release)
                        db.insert(show)

    def create_separator(self, row):
        separator = Separator(self, orient=HORIZONTAL)
        separator.grid(row=row, column=0, sticky=E + W, columnspan=4)

    def create_select_frame(self):
        self.menus = LabelFrame(master=self, text="Select:")
        self.menus.grid(row=2, column=0, sticky=E + W, columnspan=4)
        self.create_menu_name()
        self.create_menu_season()
        self.create_menu_episode()
        self.create_menu_release()
        self.menus.grid_columnconfigure(3, weight=1)

    def set_magnet_tooltip(self, value=None):
        self.magnet_button.tooltip.text = (
            "Magnet link:\n\n"
            "%s" % value
        )

    def set_torrent_tooltip(self, value=None):
        self.torrent_button.tooltip.text = (
            "Download torrent file:\n\n"
            "%s" % value
        )

    def create_toolbar(self):
        self.toolbar = Frame(master=self)
        self.toolbar.grid(row=0, column=0, sticky=E + W, columnspan=4)

        dl_img = [('disabled', PhotoImage(file="ui/download0.png")),
                  ('normal', PhotoImage(file="ui/download1.png"))]
        mg_img = [('disabled', PhotoImage(file="ui/magnet0.png")),
                  ('normal', PhotoImage(file="ui/magnet1.png"))]
        up_img = [('disabled', PhotoImage(file="ui/update0.png")),
                  ('normal', PhotoImage(file="ui/update1.png"))]
        up_all_img = [('running', PhotoImage(file="ui/stop.png")),
                      ('disabled', PhotoImage(file="ui/update0.png")),
                      ('normal', PhotoImage(file="ui/update_all1.png"))]
        search_img = [('normal', PhotoImage(file="ui/search.png"))]
        fav_img = [('added', PhotoImage(file="ui/rem_fav.png")),
                   ('normal', PhotoImage(file="ui/add_fav.png"))]
        get_fav_img = [('disabled', PhotoImage(file="ui/get_fav0.png")),
                       ('normal', PhotoImage(file="ui/get_fav1.png"))]

        self.magnet_button = StateButton(
            self.toolbar, command=self.magnet_call, image=mg_img)
        self.magnet_button.grid(row=0, column=0)
        set_tooltip(self.magnet_button)
        self.set_magnet_tooltip()

        self.torrent_button = StateButton(
            self.toolbar, command=self.torrent_call, image=dl_img)
        self.torrent_button.grid(row=0, column=1)
        set_tooltip(self.torrent_button)
        self.set_torrent_tooltip()

        separator = Separator(self.toolbar, orient=VERTICAL)
        separator.grid(row=0, column=2, sticky=N + S)

        self.up_button = StateButton(
            self.toolbar, comman=self.update_show, image=up_img)
        self.up_button.grid(column=3, row=0)

        self.up_all_button = StateButton(
            self.toolbar, command=self.update_database, image=up_all_img)
        self.up_all_button.grid(column=4, row=0)

        separator = Separator(self.toolbar, orient=VERTICAL)
        separator.grid(row=0, column=5, sticky=N + S)

        self.search_button = StateButton(
            self.toolbar, command=self.search_window, image=search_img)
        self.search_button.grid(column=6, row=0)

        separator = Separator(self.toolbar, orient=VERTICAL)
        separator.grid(row=0, column=7, sticky=N + S)

        self.fav_button = StateButton(
            self.toolbar, command=self.toggle_fav, image=fav_img)
        self.fav_button.grid(column=8, row=0)

        self.fav_list_button = StateButton(
            self.toolbar, command=self.fav_window, image=get_fav_img)
        self.fav_list_button.grid(column=9, row=0)

        self.set_download_links()
        self.set_favorite_icon()
        self.set_fav_list_icon()

    def toggle_fav(self):
        name = self.current_name

        if self.favorite:
            self.favorites.remove(name)
        else:
            self.favorites.append(name)
        self.set_favorite_icon()
        self.set_fav_list_icon()

    def set_favorite_icon(self):
        if self.favorite:
            self.fav_button.config(state="added")
        else:
            self.fav_button.config(state="normal")

    def set_fav_list_icon(self):
        if self.favorites:
            self.fav_list_button.config(state="normal")
        else:
            self.fav_list_button.config(state="disabled")

    def magnet_call(self):
        os.startfile(self.magnet_link)

    def torrent_call(self):
        self.logger.info(self.torrent_link)

    def create_menu_name(self):
        self.menu_name_var = StringVar(self)
        self.menu_name = OptionMenu(self.menus,
                                    self.menu_name_var,
                                    ())
        self.menu_name.grid(row=0, column=0)
        self.menu_name.bind("<Key>", self.search_name)
        self.reset_menu_name()

    def reset_menu_name(self, name=None):
        names = self.names
        if name is None:
            index = 0
        else:
            index = names.index(name)

        self.reset_menu(menu=self.menu_name,
                        variable=self.menu_name_var,
                        command=self.change_name,
                        options=names,
                        index=index)

    def create_menu_season(self):
        self.menu_season_var = IntVar(self)
        self.menu_season = OptionMenu(self.menus,
                                      self.menu_season_var,
                                      ())
        self.menu_season.grid(row=0, column=1)
        self.reset_menu_season()

    def reset_menu_season(self):
        seasons = self.seasons
        self.reset_menu(menu=self.menu_season,
                        variable=self.menu_season_var,
                        command=self.change_season,
                        options=seasons,
                        index=0)

    def create_menu_episode(self):
        self.menu_episode_var = IntVar(self)
        self.menu_episode = OptionMenu(self.menus,
                                       self.menu_episode_var,
                                       ())
        self.menu_episode.grid(row=0, column=2)
        self.reset_menu_episode()

    def reset_menu_episode(self):
        episodes = self.episodes
        self.reset_menu(menu=self.menu_episode,
                        variable=self.menu_episode_var,
                        command=self.change_episode,
                        options=episodes,
                        index=0)

    def create_menu_release(self):
        self.menu_release_var = StringVar(self)
        self.menu_release = OptionMenu(self.menus,
                                       self.menu_release_var,
                                       ())
        self.menu_release.grid(row=0, column=3, columnspan=2, sticky=E + W)
        self.reset_menu_release()

    def reset_menu_release(self):
        releases = self.releases
        self.reset_menu(menu=self.menu_release,
                        variable=self.menu_release_var,
                        command=self.change_release,
                        options=releases,
                        index=0)
        try:
            self.change_release()
        except AttributeError:
            pass

    def reset_menu(self, menu, variable, command, options, index=None):
        menu = menu["menu"]
        menu.delete(0, "end")
        for string in options:
            menu.add_command(
                label=string,
                command=lambda value=string: command(value))
        if index is not None:
            variable.set(options[index])

    @property
    def favorite(self):
        return self.current_name in self.favorites

    def change_name(self, value):
        self.menu_name_var.set(value)

        self.set_favorite_icon()
        self.set_fav_list_icon()

        self._seasons = None
        self.reset_menu_season()
        self._episodes = None
        self.reset_menu_episode()
        self._releases = None
        self.reset_menu_release()

    @property
    def current_name(self):
        return self.menu_name_var.get()

    def change_season(self, value):
        old_season = self.current_season
        if value != old_season:
            self.menu_season_var.set(value)
            self._episodes = None
            self.reset_menu_episode()
            self._releases = None
            self.reset_menu_release()
            # print("change_season", self.current_season)

    @property
    def current_season(self):
        try:
            return self.menu_season_var.get()
        except TclError:
            return None

    def change_episode(self, value):
        old_episode = self.current_episode
        if value != old_episode:
            self.menu_episode_var.set(value)
            self._releases = None
            self.reset_menu_release()
            # print("change_episode", self.current_episode)

    @property
    def current_episode(self):
        try:
            return self.menu_episode_var.get()
        except TclError:
            return None

    def change_release(self, value=None):
        old_release = self.current_release
        if value != old_release:
            if value is not None:
                self.menu_release_var.set(value)
            self.set_download_links()

    @property
    def current_release(self):
        try:
            return self.menu_release_var.get()
        except TclError:
            return None

    @property
    def names(self):
        if getattr(self, "_names", None) is None:
            self.logger.info("caching names...")
            self._names = sorted(set((
                item["name"] for item in self.db.all)))
        return self._names

    @property
    def seasons(self):
        if getattr(self, "_seasons", None) is None:
            self.logger.info("caching seasons...")
            tv = Query()
            search = (tv.name == self.current_name)
            self._current_tv = [element
                                for element in self.db.all
                                if search(element)]

            self._seasons = sorted(set((item["season"]
                                        for item in self._current_tv)))
        return self._seasons

    @property
    def episodes(self):
        if getattr(self, "_episodes", None) is None:
            self.logger.info("caching episodes...")
            tv = Query()
            search = (tv.season == self.current_season)
            self._episodes = sorted(set((
                element["episode"]
                for element in self._current_tv if search(element))))
        return self._episodes

    @property
    def releases(self):
        if getattr(self, "_releases", None) is None:
            tv = Query()
            search = (
                (tv.season == self.current_season) &
                (tv.episode == self.current_episode)
            )
            self._releases = sorted(set((
                element["release"]
                for element in self._current_tv if search(element))))
        return self._releases

    @property
    def torrent_link(self):
        if getattr(self, "_torrent_link", None) is None:
            self.set_download_links()
        return self._torrent_link

    @property
    def magnet_link(self):
        if getattr(self, "_magnet_link", None) is None:
            self.set_download_links()
        return self._magnet_link

    def set_download_links(self):
        tv = Query()
        search = (
            (tv.season == self.current_season) &
            (tv.episode == self.current_episode) &
            (tv.release == self.current_release)
        )
        links = sorted((
            element
            for element in self._current_tv
            if search(element)))
        if links:
            links = links[0]
            self._torrent_link = links["torrents"] or None
            self._magnet_link = links["magnet"] or None
        else:
            self._torrent_link = None
            self._magnet_link = None

        if self._torrent_link is None:
            self.set_torrent_tooltip()
            self.torrent_button.config(state="disabled")
        else:
            self._torrent_link = self._torrent_link[0]
            self.set_torrent_tooltip(self._torrent_link)
            self.torrent_button.config(state="normal")

        if self._magnet_link is None:
            self.set_magnet_tooltip()
            self.magnet_button.config(state="disabled")
        else:
            self.set_magnet_tooltip(self._magnet_link)
            self.magnet_button.config(state="normal")
        self.update()


class SearchWindow(tk.Toplevel):

    label_text = "Show Name"
    window_title = "Search"
    window_icon = "ui/search.ico"

    def entry_change(self, *args):
        string = self.entry_var.get().lower()
        self.list.delete(0, END)
        if string:
            names = [name
                     for name in self.main_w.names
                     if name.lower().startswith(string)]
            if names:
                self.list.insert(0, *names)

    def __init__(self, main_w):
        super().__init__()

        self.main_w = main_w

        self.label = Label(self, text=self.label_text)
        self.label.grid(row=0, column=0)

        self.entry_var = StringVar()
        self.entry = Entry(self, textvariable=self.entry_var)
        self.entry.grid(row=0, column=1)
        self.entry_var.trace("w", self.entry_change)
        # sv.trace("w", lambda name, index, mode, sv=sv: callback(sv))

        separator = Separator(self, orient=HORIZONTAL)
        separator.grid(row=1, column=0, sticky=E + W)

        self.list = Listbox(self, height=10)
        self.list.grid(column=0, row=2, sticky=(E + W), columnspan=4)

        self.scroll = Scrollbar(
            self, orient=VERTICAL, command=self.list.yview)
        self.scroll.grid(column=5, row=2, sticky=(N, S))

        self.list['yscrollcommand'] = self.scroll.set

        self.list.bind(
            "<<ListboxSelect>>", self.on_listbox_select)

        self.update()

        height = self.main_w.winfo_height() // 3
        width = self.main_w.winfo_width() // 3

        self.geometry("+%d+%d" % (self.main_w.winfo_rootx() + width,
                                  self.main_w.winfo_rooty() + height))

        self.title(self.window_title)
        self.iconbitmap(self.window_icon)
        self.entry_change()
        self.focus_set()

    def on_listbox_select(self, event):
        i = self.list.curselection()[0]
        text = self.list.get(i)
        # self.main_w.menu_name_var.set(text)
        self.main_w.update_gui(text)


class FavWindow(SearchWindow):

    label_text = "Favorite Show Name"
    window_title = "Favorites"
    window_icon = "ui/favorites.ico"

    def entry_change(self, *args):
        string = self.entry_var.get().lower()
        self.list.delete(0, END)
        if string:
            names = [name
                     for name in self.main_w.favorites
                     if name.lower().startswith(string)]
            if names:
                self.list.insert(0, *names)
        else:
            names = [name
                     for name in self.main_w.favorites]
            if names:
                self.list.insert(0, *names)


class StateButton(Button):

    def __init__(self, master, image, *args, **kwargs):
        self.state_images = image
        state = kwargs.pop('state', None)

        super().__init__(master, image=image[-1][-1], *args, **kwargs)

        if state:
            self.config(state=state)

    def config(self, **kwargs):
        new_state = kwargs.pop('state', None)
        if new_state:
            for (states, img) in self.state_images:
                if new_state in states:
                    super().config(image=img)
                    break
            super().config(state=new_state)
        if kwargs:
            super().config(kwargs)


class LogHandler(logging.StreamHandler):

    def __init__(self, widget):
        def ipinfo(self, message, *args, **kws):
            # Yes, logger takes its '*args' as 'args'.
            if self.isEnabledFor(25):
                self._log(25, message, args, **kws)

        logging.StreamHandler.__init__(self)  # initialize parent
        self.setLevel(logging.DEBUG)
        self.widget = widget
        logging.addLevelName(25, "IPINFO")

        self.widget.tag_config("DEBUG", foreground="grey")
        self.widget.tag_config("INFO", foreground="green")
        self.widget.tag_config("IPINFO", foreground="blue")
        self.widget.tag_config("WARNING", foreground="orange")
        self.widget.tag_config("ERROR", foreground="red")
        self.widget.tag_config("CRITICAL", foreground="red", underline=1)

        self.red = self.widget.tag_configure("red", foreground="red")

        logging.Logger.ipinfo = ipinfo

    def emit(self, record):
        self.widget.config(state="normal")
        self.widget.insert(
            tk.END, self.format(record) + '\n', record.levelname)
        self.widget.see(tk.END)  # Scroll to the bottom
        self.widget.config(state="disabled")
        self.widget.update()  # Refresh the widget
