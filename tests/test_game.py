"""Headless tests. Run with: python -m unittest discover -s tests"""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from drachewut import client, world  # noqa: E402
from drachewut.paths import ASSETS  # noqa: E402
from drachewut.player import CLASSES, Player  # noqa: E402

MAPS = sorted(p.name for p in (ASSETS / "maps").glob("*.map"))


def setUpModule():
    pygame.init()
    pygame.display.set_mode(client.SCREEN_SIZE)


def tearDownModule():
    pygame.quit()


class MapTests(unittest.TestCase):
    def test_every_map_loads_with_a_rectangular_grid(self):
        for name in MAPS:
            with self.subTest(name):
                m = world.GameMap(name)
                self.assertGreater(m.rows, 0)
                self.assertTrue(all(len(row) == m.cols for row in m.grid))

    def test_every_tile_code_is_in_the_tileset(self):
        tiles = world.TileDbase()
        for name in MAPS:
            m = world.GameMap(name)
            unknown = {code for row in m.grid for code in row} - set(tiles.cells)
            self.assertFalse(unknown, f"{name}: {sorted(unknown)}")

    def test_warp_targets_exist_and_arrivals_are_walkable(self):
        zone = world.Zone()
        for name in MAPS:
            for w in world.GameMap(name).warps:
                with self.subTest(f"{name} -> {w.target}"):
                    self.assertIn(w.target, MAPS)
                    zone.map = world.GameMap(name)
                    x, y = zone.enter(w.target, w.dest)
                    self.assertNotEqual(zone.tile_effect(x, y), world.BLOCK)

    def test_damage_tile_is_not_a_wall(self):
        # master.con says "block = False" for b02; a truthiness test read that as a wall.
        self.assertEqual(world.TileDbase().effect("b02"), world.DAMAGE)


class ZoneTests(unittest.TestCase):
    def setUp(self):
        self.zone = world.Zone()

    def test_walls_push_the_player_out(self):
        # Hub tile (row 5, col 11) is the lava gate in front of the volcano
        # portal. Walking up into it from below stops at its bottom edge.
        x, y = self.zone.collide(11 * 64 + 32, 6 * 64 + 2)
        self.assertGreaterEqual(y, 6 * 64 + 8 - 0.01)
        # The map edge also blocks.
        x, y = self.zone.collide(768, 2)
        self.assertGreaterEqual(y, 8 - 0.01)

    def test_stepping_onto_a_portal_warps_and_arriving_does_not_bounce(self):
        hub = self.zone.map
        portal = next(w for w in hub.warps if w.target == "forest.map")
        px = portal.col * world.TILE_SIZE + 32
        py = portal.row * world.TILE_SIZE + 32
        self.assertIsNone(self.zone.check_warp(px, py + 2 * world.TILE_SIZE))  # arms
        arrival = self.zone.check_warp(px, py)
        self.assertIsNotNone(arrival)
        self.assertEqual(self.zone.map.name, "forest.map")
        # Standing on the arrival portal must not warp back.
        self.assertIsNone(self.zone.check_warp(*arrival))
        self.assertEqual(self.zone.map.name, "forest.map")


class PlayerTests(unittest.TestCase):
    def test_every_class_loads_its_sprites(self):
        for cls in CLASSES:
            p = Player("t", cls)
            self.assertEqual(len(p.frames), 8)
            self.assertEqual(len(p.death_frames), 8)

    def test_diagonal_speed_is_normalized(self):
        p = Player("t", "Thief")
        p.set_move(1, 1)
        p.update(1.0)
        moved = ((p.posX - 768) ** 2 + (p.posY - 640) ** 2) ** 0.5
        self.assertAlmostEqual(moved, 250.0, places=3)
        self.assertEqual(p.walkdir, 4)  # south-east

    def test_serialize_roundtrip_and_updates_carry_position(self):
        a = Player("ann", "Mage", load_sprites=False)
        a.posX, a.posY, a.walkdir = 100, 200, 3
        b = Player("bob", load_sprites=False)
        b.deserialize(a.serialize(2))
        self.assertEqual((b.posX, b.posY, b.walkdir, b.Pclass), (100, 200, 3, "Mage"))
        a.posX = 150
        update = a.serialize(0)
        self.assertIn("x=150", update)
        self.assertEqual(a.serialize(0), "")  # nothing changed since

    def test_death_and_respawn(self):
        p = Player("t")
        p.hurt(1000)
        self.assertTrue(p.dead)
        p.update(3.0)
        self.assertTrue(p.respawn_due())
        p.respawn(10, 20)
        self.assertFalse(p.dead)


class OfflineClientTests(unittest.TestCase):
    def test_play_offline_and_take_damage(self):
        app = client.Application()
        app.classstr = "Warrior"
        app.startOffline()
        me = app.players[0]
        self.assertEqual((app.gameState, me.Pclass, app.map.map.name), ("Game", "Warrior", "hub.map"))
        app.update(1 / 60)
        app.render()

        # Put the player on a damage tile in the hub, if there is one.
        tiles, grid = app.map.tiles, app.map.map.grid
        spots = [(r, c) for r, row in enumerate(grid) for c, code in enumerate(row)
                 if tiles.effect(code) == world.DAMAGE]
        if spots:
            r, c = spots[0]
            me.posX, me.posY = c * 64 + 32, r * 64 + 32
            app.update(0.1)
            self.assertLess(me.cur_health, me.max_health)

    def test_a_quick_tap_moves_the_player(self):
        app = client.Application()
        app.startOffline()
        me = app.players[0]
        x = me.posX
        app.keyDown(pygame.K_RIGHT, 0)  # pressed and released before the frame
        app.update(0.05)
        self.assertGreater(me.posX, x)

    def test_offline_chat_is_echoed(self):
        app = client.Application()
        app.startOffline()
        app.sendChat("hello")
        self.assertIn(f"{app.uname}: hello", app.chat_log.lines)


class MultiplayerTests(unittest.TestCase):
    """A real server and two clients talking over loopback UDP."""

    def setUp(self):
        from drachewut.server import Server

        self.tmp = tempfile.TemporaryDirectory()
        self.server = Server(5, 0, Path(self.tmp.name) / "accounts.dat", log_level=-1)
        self.server.loadDBase()
        self.port = self.server.connection.getLocalPort()
        self.apps = []

    def tearDown(self):
        for app in self.apps:
            app.leaveGame()
        self.server.connection.close()
        self.tmp.cleanup()

    def pump(self, n=40):
        for _ in range(n):
            self.server.step(1 / 60)
            for app in self.apps:
                app.updateConnection()

    def join(self, name, create):
        app = client.Application()
        self.apps.append(app)
        app.connectToServer(name, "pw", "Thief", create, "127.0.0.1", self.port)
        app.connection._log_level = -1
        self.pump()
        return app

    def test_signup_login_movement_and_chat(self):
        a = self.join("ann", create=True)
        self.assertEqual(a.gameState, "Game")
        self.assertIn("ann", self.server.dbase)

        # A second account; then log in to an existing account.
        self.join("bob", create=True)
        a.leaveGame()
        self.pump()
        a2 = self.join("ann", create=False)
        self.assertEqual(a2.gameState, "Game")

        b = self.apps[1]
        me = a2.players[a2.playerID]
        me.posX, me.posY = 900, 700
        self.pump(60)
        self.assertIn(a2.playerID, b.players)
        self.assertEqual((b.players[a2.playerID].posX, b.players[a2.playerID].posY), (900, 700))

        a2.sendChat("ahoy")
        self.pump()
        self.assertIn("ann: ahoy", b.chat_log.lines)

    def test_wrong_password_is_rejected(self):
        self.join("cat", create=True)
        app = client.Application()
        self.apps.append(app)
        app.connectToServer("cat", "nope", None, False, "127.0.0.1", self.port)
        self.pump()
        self.assertEqual(app.gameState, "login_failure")


if __name__ == "__main__":
    unittest.main()
