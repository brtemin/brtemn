"""
================================================================================
  NEON STRIKE - Profesyonel Tam Ekran Silah Oyunu (Top-Down Arena Shooter)
================================================================================
  Gereksinimler:
      pip install pygame
  Çalıştırma:
      python silah_oyunu.py

  Kontroller:
      WASD / Ok tuşları : Hareket
      Fare              : Nişan al
      Sol Tık           : Ateş et
      1-2-3-4           : Silah değiştir (Tabanca / SMG / Shotgun / Sniper)
      R                 : Şarjör değiştir (Reload)
      Shift             : Sprint (koşma)
      Space             : Dash (kısa atılma)
      ESC               : Pause / Menü
      F11               : Tam ekran aç/kapat
      F1                : FPS göster
================================================================================
"""

import pygame
import math
import random
import os
import json
import sys
from pygame import gfxdraw

# ============================================================================
# BÖLÜM 1: SABİTLER VE KONFİGÜRASYON
# ============================================================================

GAME_TITLE        = "NEON STRIKE"
GAME_VERSION      = "1.0.0"
TARGET_FPS        = 60
SAVE_FILE         = "neonstrike_save.json"

# Varsayılan çözünürlük (fullscreen değilken)
DEFAULT_WIDTH     = 1280
DEFAULT_HEIGHT    = 720

# Arena boyutu (kameranın hareket ettiği dünya)
WORLD_WIDTH       = 2400
WORLD_HEIGHT      = 1600

# Renkler (Neon teması)
C_BG_DARK         = (10, 12, 22)
C_BG_GRID         = (22, 26, 44)
C_BG_GRID_BRIGHT  = (40, 50, 80)
C_WHITE           = (240, 245, 255)
C_BLACK           = (0, 0, 0)
C_NEON_CYAN       = (0, 240, 255)
C_NEON_PINK       = (255, 60, 180)
C_NEON_GREEN      = (80, 255, 140)
C_NEON_YELLOW     = (255, 230, 80)
C_NEON_PURPLE     = (180, 90, 255)
C_NEON_ORANGE     = (255, 140, 40)
C_NEON_RED        = (255, 60, 80)
C_HUD_BG          = (16, 18, 30)
C_HUD_BORDER      = (60, 80, 120)
C_HUD_DIM         = (90, 100, 130)
C_DAMAGE_FLASH    = (255, 40, 40)

# Oyuncu sabitleri
PLAYER_RADIUS     = 18
PLAYER_SPEED      = 260           # px/saniye
PLAYER_SPRINT_MUL = 1.55
PLAYER_MAX_HP     = 100
PLAYER_MAX_ARMOR  = 100
DASH_SPEED        = 900
DASH_DURATION     = 0.18
DASH_COOLDOWN     = 1.2

# Düşman sabitleri
ENEMY_SPAWN_MARGIN = 80

# Particle / efekt
MAX_PARTICLES      = 800

# ============================================================================
# BÖLÜM 2: YARDIMCI MATEMATİK FONKSİYONLARI
# ============================================================================

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def lerp(a, b, t):
    return a + (b - a) * t

def length(v):
    return math.hypot(v[0], v[1])

def normalize(v):
    l = math.hypot(v[0], v[1])
    if l == 0:
        return (0.0, 0.0)
    return (v[0] / l, v[1] / l)

def angle_to(p1, p2):
    return math.atan2(p2[1] - p1[1], p2[0] - p1[0])

def dist(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def dist_sq(p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return dx * dx + dy * dy

def lerp_color(c1, c2, t):
    t = clamp(t, 0.0, 1.0)
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))

def with_alpha(c, a):
    return (c[0], c[1], c[2], int(clamp(a, 0, 255)))

def rotate_point(px, py, angle):
    c, s = math.cos(angle), math.sin(angle)
    return (px * c - py * s, px * s + py * c)

def shortest_angle_diff(a, b):
    d = (b - a) % (2 * math.pi)
    if d > math.pi:
        d -= 2 * math.pi
    return d


# ============================================================================
# BÖLÜM 3: SES MOTORU (Procedural - dosya gerektirmez)
# ============================================================================

class SoundEngine:
    """pygame.sndarray ile prosedürel ses üretir. Numpy yoksa sessiz çalışır."""

    def __init__(self):
        self.enabled = True
        self.cache = {}
        self.master_volume = 0.5
        try:
            pygame.mixer.pre_init(44100, -16, 2, 256)
            pygame.mixer.init()
            import numpy  # noqa
            self.numpy_ok = True
        except Exception:
            self.numpy_ok = False
            self.enabled = False

    def _make(self, key, freq=440.0, duration=0.1, vol=0.4, kind="sine", sweep=0.0):
        if not self.enabled:
            return None
        if key in self.cache:
            return self.cache[key]
        try:
            import numpy as np
            sample_rate = 44100
            n = max(8, int(sample_rate * duration))
            t = np.arange(n) / sample_rate
            if kind == "sine":
                f = freq + sweep * t
                wave = np.sin(2 * np.pi * f * t)
            elif kind == "square":
                f = freq + sweep * t
                wave = np.sign(np.sin(2 * np.pi * f * t))
            elif kind == "saw":
                f = freq + sweep * t
                wave = 2 * (t * f - np.floor(0.5 + t * f))
            elif kind == "noise":
                wave = np.random.uniform(-1, 1, n)
            else:
                wave = np.sin(2 * np.pi * freq * t)
            # ADSR zarfı
            env = np.ones(n)
            attack = max(1, int(0.005 * sample_rate))
            release = max(1, int(0.05 * sample_rate))
            env[:attack] = np.linspace(0, 1, attack)
            env[-release:] = np.linspace(1, 0, release)
            wave = wave * env * vol
            audio = (wave * 32767).astype(np.int16)
            stereo = np.column_stack((audio, audio))
            sound = pygame.sndarray.make_sound(stereo)
            self.cache[key] = sound
            return sound
        except Exception:
            self.enabled = False
            return None

    def play(self, key, **kwargs):
        if not self.enabled:
            return
        s = self._make(key, **kwargs)
        if s:
            s.set_volume(self.master_volume)
            s.play()

    def shoot_pistol(self):
        self.play("shoot_pistol", freq=720, duration=0.07, vol=0.35, kind="square", sweep=-3000)

    def shoot_smg(self):
        self.play("shoot_smg", freq=540, duration=0.05, vol=0.28, kind="square", sweep=-2200)

    def shoot_shotgun(self):
        self.play("shoot_shotgun", freq=180, duration=0.16, vol=0.5, kind="noise")

    def shoot_sniper(self):
        self.play("shoot_sniper", freq=300, duration=0.22, vol=0.55, kind="saw", sweep=-1500)

    def reload(self):
        self.play("reload", freq=220, duration=0.18, vol=0.3, kind="square")

    def hit(self):
        self.play("hit", freq=900, duration=0.06, vol=0.3, kind="sine", sweep=-2000)

    def explosion(self):
        self.play("explosion", freq=120, duration=0.4, vol=0.7, kind="noise")

    def pickup(self):
        self.play("pickup", freq=880, duration=0.12, vol=0.35, kind="sine", sweep=2400)

    def damage(self):
        self.play("damage", freq=180, duration=0.2, vol=0.5, kind="square", sweep=-800)

    def click(self):
        self.play("click", freq=600, duration=0.04, vol=0.25, kind="square")

    def wave_start(self):
        self.play("wave_start", freq=300, duration=0.5, vol=0.5, kind="sine", sweep=600)


# ============================================================================
# BÖLÜM 4: PARTİKÜL SİSTEMİ
# ============================================================================

class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size",
                 "color", "fade", "gravity", "shrink", "kind")

    def __init__(self, x, y, vx, vy, life, size, color,
                 fade=True, gravity=0.0, shrink=True, kind="circle"):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.size = size
        self.color = color
        self.fade = fade
        self.gravity = gravity
        self.shrink = shrink
        self.kind = kind

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt
        # hafif sürtünme
        self.vx *= 0.985
        self.vy *= 0.985
        self.life -= dt
        return self.life > 0


class ParticleSystem:
    def __init__(self):
        self.particles = []

    def emit(self, x, y, count, color, speed=180, life=0.5, size=4,
             spread=math.pi * 2, base_angle=0.0, gravity=0.0, kind="circle"):
        for _ in range(count):
            a = base_angle + random.uniform(-spread / 2, spread / 2)
            sp = speed * random.uniform(0.4, 1.2)
            vx = math.cos(a) * sp
            vy = math.sin(a) * sp
            sz = size * random.uniform(0.6, 1.3)
            lf = life * random.uniform(0.7, 1.3)
            p = Particle(x, y, vx, vy, lf, sz, color, gravity=gravity, kind=kind)
            self.particles.append(p)
        # hard cap
        if len(self.particles) > MAX_PARTICLES:
            self.particles = self.particles[-MAX_PARTICLES:]

    def burst_blood(self, x, y, color=C_NEON_RED):
        self.emit(x, y, 14, color, speed=240, life=0.45, size=4)

    def burst_spark(self, x, y, color=C_NEON_YELLOW, base_angle=0.0):
        self.emit(x, y, 8, color, speed=320, life=0.25, size=3,
                  spread=math.pi / 2, base_angle=base_angle)

    def burst_explosion(self, x, y):
        self.emit(x, y, 40, C_NEON_ORANGE, speed=380, life=0.6, size=6)
        self.emit(x, y, 25, C_NEON_YELLOW, speed=280, life=0.5, size=4)
        self.emit(x, y, 15, (80, 80, 90), speed=160, life=0.9, size=5)

    def smoke(self, x, y):
        self.emit(x, y, 4, (90, 90, 110), speed=60, life=0.8, size=6,
                  gravity=-40)

    def update(self, dt):
        self.particles = [p for p in self.particles if p.update(dt)]

    def draw(self, surf, camera):
        for p in self.particles:
            t = clamp(p.life / p.max_life, 0, 1)
            sz = max(1, int(p.size * (t if p.shrink else 1)))
            alpha = int(255 * t) if p.fade else 255
            col = with_alpha(p.color, alpha)
            sx = int(p.x - camera.x)
            sy = int(p.y - camera.y)
            if sx < -20 or sy < -20 or sx > camera.w + 20 or sy > camera.h + 20:
                continue
            s = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, col, (sz, sz), sz)
            surf.blit(s, (sx - sz, sy - sz), special_flags=pygame.BLEND_PREMULTIPLIED)


# ============================================================================
# BÖLÜM 5: KAMERA
# ============================================================================

class Camera:
    def __init__(self, w, h):
        self.x = 0.0
        self.y = 0.0
        self.w = w
        self.h = h
        self.shake_amount = 0.0
        self.shake_decay = 6.0
        self.offset_x = 0.0
        self.offset_y = 0.0

    def resize(self, w, h):
        self.w = w
        self.h = h

    def follow(self, target_x, target_y, dt, smooth=8.0):
        cx = target_x - self.w / 2
        cy = target_y - self.h / 2
        self.x = lerp(self.x, cx, clamp(dt * smooth, 0, 1))
        self.y = lerp(self.y, cy, clamp(dt * smooth, 0, 1))
        self.x = clamp(self.x, 0, WORLD_WIDTH - self.w)
        self.y = clamp(self.y, 0, WORLD_HEIGHT - self.h)

        if self.shake_amount > 0.01:
            self.offset_x = random.uniform(-self.shake_amount, self.shake_amount)
            self.offset_y = random.uniform(-self.shake_amount, self.shake_amount)
            self.shake_amount = max(0, self.shake_amount - self.shake_decay * dt * self.shake_amount)
        else:
            self.offset_x = 0
            self.offset_y = 0

    def shake(self, amount):
        self.shake_amount = max(self.shake_amount, amount)

    def world_to_screen(self, wx, wy):
        return (wx - self.x + self.offset_x, wy - self.y + self.offset_y)

    def screen_to_world(self, sx, sy):
        return (sx + self.x - self.offset_x, sy + self.y - self.offset_y)


# ============================================================================
# BÖLÜM 6: SİLAH SİSTEMİ
# ============================================================================

class Weapon:
    """Silah veri ve davranış konteyneri."""

    def __init__(self, name, dmg, fire_rate, mag, reserve_max, reload_time,
                 spread, bullet_speed, color, pellets=1, recoil=4.0,
                 sound=None, full_auto=True, range_=1400, key=None):
        self.name = name
        self.damage = dmg
        self.fire_rate = fire_rate           # mermi/saniye
        self.mag_size = mag
        self.mag = mag
        self.reserve_max = reserve_max
        self.reserve = reserve_max
        self.reload_time = reload_time
        self.spread = spread                  # radyan
        self.bullet_speed = bullet_speed
        self.color = color
        self.pellets = pellets
        self.recoil = recoil
        self.sound = sound
        self.full_auto = full_auto
        self.range = range_
        self.key = key
        self._fire_cd = 0.0
        self._reload_t = 0.0
        self._reloading = False

    def update(self, dt):
        if self._fire_cd > 0:
            self._fire_cd -= dt
        if self._reloading:
            self._reload_t -= dt
            if self._reload_t <= 0:
                self._reloading = False
                need = self.mag_size - self.mag
                take = min(need, self.reserve)
                self.mag += take
                self.reserve -= take

    def can_fire(self):
        return (not self._reloading) and self._fire_cd <= 0 and self.mag > 0

    def fire(self):
        self.mag -= 1
        self._fire_cd = 1.0 / self.fire_rate

    def reload(self, sound_engine=None):
        if self._reloading:
            return False
        if self.mag >= self.mag_size or self.reserve <= 0:
            return False
        self._reloading = True
        self._reload_t = self.reload_time
        if sound_engine:
            sound_engine.reload()
        return True

    def add_ammo(self, amount):
        self.reserve = min(self.reserve_max, self.reserve + amount)

    def reload_progress(self):
        if not self._reloading:
            return 1.0
        return 1.0 - (self._reload_t / self.reload_time)


def make_default_weapons():
    return [
        Weapon("Pistol", dmg=22, fire_rate=5.5, mag=14, reserve_max=120,
               reload_time=1.1, spread=0.04, bullet_speed=1500,
               color=C_NEON_CYAN, recoil=3.0, sound="pistol",
               full_auto=False, range_=1300, key=pygame.K_1),
        Weapon("SMG", dmg=14, fire_rate=14.0, mag=32, reserve_max=240,
               reload_time=1.6, spread=0.10, bullet_speed=1400,
               color=C_NEON_GREEN, recoil=2.2, sound="smg",
               full_auto=True, range_=1100, key=pygame.K_2),
        Weapon("Shotgun", dmg=14, fire_rate=1.6, mag=6, reserve_max=48,
               reload_time=2.2, spread=0.30, bullet_speed=1200,
               color=C_NEON_ORANGE, pellets=8, recoil=12.0, sound="shotgun",
               full_auto=False, range_=700, key=pygame.K_3),
        Weapon("Sniper", dmg=120, fire_rate=1.1, mag=5, reserve_max=30,
               reload_time=2.4, spread=0.005, bullet_speed=2400,
               color=C_NEON_PURPLE, recoil=18.0, sound="sniper",
               full_auto=False, range_=2200, key=pygame.K_4),
    ]


# ============================================================================
# BÖLÜM 7: MERMİLER
# ============================================================================

class Bullet:
    __slots__ = ("x", "y", "vx", "vy", "damage", "color", "life",
                 "owner", "size", "trail", "pierce", "max_dist", "traveled")

    def __init__(self, x, y, vx, vy, damage, color, owner="player",
                 size=4, pierce=0, max_dist=1400):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.color = color
        self.life = 1.5
        self.owner = owner
        self.size = size
        self.trail = []
        self.pierce = pierce
        self.max_dist = max_dist
        self.traveled = 0.0

    def update(self, dt):
        self.trail.append((self.x, self.y))
        if len(self.trail) > 6:
            self.trail.pop(0)
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        self.traveled += math.hypot(self.vx, self.vy) * dt
        self.x = nx
        self.y = ny
        self.life -= dt
        if self.x < 0 or self.y < 0 or self.x > WORLD_WIDTH or self.y > WORLD_HEIGHT:
            return False
        if self.traveled > self.max_dist:
            return False
        return self.life > 0

    def draw(self, surf, camera):
        sx, sy = camera.world_to_screen(self.x, self.y)
        if sx < -10 or sy < -10 or sx > camera.w + 10 or sy > camera.h + 10:
            return
        # iz
        if len(self.trail) >= 2:
            pts = [camera.world_to_screen(tx, ty) for tx, ty in self.trail]
            pts.append((sx, sy))
            try:
                pygame.draw.lines(surf, self.color, False, pts, 2)
            except Exception:
                pass
        # parlak çekirdek
        pygame.draw.circle(surf, C_WHITE, (int(sx), int(sy)), self.size)
        glow = pygame.Surface((self.size * 6, self.size * 6), pygame.SRCALPHA)
        pygame.draw.circle(glow, with_alpha(self.color, 90),
                           (self.size * 3, self.size * 3), self.size * 3)
        surf.blit(glow, (sx - self.size * 3, sy - self.size * 3),
                  special_flags=pygame.BLEND_PREMULTIPLIED)


# ============================================================================
# BÖLÜM 8: OYUNCU
# ============================================================================

class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = 0
        self.vy = 0
        self.r = PLAYER_RADIUS
        self.hp = PLAYER_MAX_HP
        self.max_hp = PLAYER_MAX_HP
        self.armor = 0
        self.max_armor = PLAYER_MAX_ARMOR
        self.aim_angle = 0.0
        self.weapons = make_default_weapons()
        self.weapon_idx = 0
        self.recoil_offset = 0.0
        self.muzzle_flash = 0.0
        self.dash_t = 0.0
        self.dash_cd = 0.0
        self.dash_dir = (0, 0)
        self.invuln = 0.0
        self.damage_flash = 0.0
        self.score = 0
        self.gold = 0
        self.kills = 0
        self.alive = True
        self.walk_anim = 0.0

    @property
    def weapon(self):
        return self.weapons[self.weapon_idx]

    def switch_weapon(self, idx, sound_engine=None):
        if 0 <= idx < len(self.weapons) and idx != self.weapon_idx:
            self.weapon_idx = idx
            if sound_engine:
                sound_engine.click()

    def take_damage(self, dmg, sound_engine=None):
        if self.invuln > 0 or not self.alive:
            return
        # Önce zırh
        absorbed = min(self.armor, dmg * 0.6)
        self.armor -= absorbed
        self.hp -= (dmg - absorbed)
        self.damage_flash = 0.4
        self.invuln = 0.4
        if sound_engine:
            sound_engine.damage()
        if self.hp <= 0:
            self.hp = 0
            self.alive = False

    def heal(self, amount):
        self.hp = min(self.max_hp, self.hp + amount)

    def add_armor(self, amount):
        self.armor = min(self.max_armor, self.armor + amount)

    def start_dash(self, dir_x, dir_y):
        if self.dash_cd > 0 or self.dash_t > 0:
            return
        n = math.hypot(dir_x, dir_y)
        if n == 0:
            dir_x = math.cos(self.aim_angle)
            dir_y = math.sin(self.aim_angle)
            n = 1
        self.dash_dir = (dir_x / n, dir_y / n)
        self.dash_t = DASH_DURATION
        self.dash_cd = DASH_COOLDOWN
        self.invuln = max(self.invuln, DASH_DURATION + 0.05)

    def update(self, dt, keys, mouse_world, sound_engine):
        if not self.alive:
            return
        # Hareket girdisi
        mx = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - \
             (1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0)
        my = (1 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0) - \
             (1 if keys[pygame.K_w] or keys[pygame.K_UP] else 0)
        moving = (mx != 0 or my != 0)
        if moving:
            n = math.hypot(mx, my)
            mx /= n
            my /= n
        speed = PLAYER_SPEED
        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
            speed *= PLAYER_SPRINT_MUL

        # Dash
        if self.dash_t > 0:
            self.x += self.dash_dir[0] * DASH_SPEED * dt
            self.y += self.dash_dir[1] * DASH_SPEED * dt
            self.dash_t -= dt
        else:
            self.x += mx * speed * dt
            self.y += my * speed * dt

        if self.dash_cd > 0:
            self.dash_cd -= dt

        # Sınırlar
        self.x = clamp(self.x, self.r, WORLD_WIDTH - self.r)
        self.y = clamp(self.y, self.r, WORLD_HEIGHT - self.r)

        # Nişan
        self.aim_angle = math.atan2(mouse_world[1] - self.y,
                                    mouse_world[0] - self.x)

        # Recoil decay
        self.recoil_offset = lerp(self.recoil_offset, 0, clamp(dt * 8, 0, 1))
        if self.muzzle_flash > 0:
            self.muzzle_flash -= dt
        if self.invuln > 0:
            self.invuln -= dt
        if self.damage_flash > 0:
            self.damage_flash -= dt

        # Walk animasyonu
        if moving and self.dash_t <= 0:
            self.walk_anim += dt * 12
        else:
            self.walk_anim = 0

        # Silah güncelle
        for w in self.weapons:
            w.update(dt)

        # Pasif zırh erimesi yok; hp regen yok (zorluk için)

    def fire(self, bullets, particles, camera, sound_engine):
        w = self.weapon
        if not w.can_fire():
            if w.mag == 0 and not w._reloading:
                w.reload(sound_engine)
            return
        w.fire()
        # Namlu ucu
        bx = self.x + math.cos(self.aim_angle) * (self.r + 14)
        by = self.y + math.sin(self.aim_angle) * (self.r + 14)
        for _ in range(w.pellets):
            spread = random.uniform(-w.spread, w.spread)
            ang = self.aim_angle + spread
            vx = math.cos(ang) * w.bullet_speed
            vy = math.sin(ang) * w.bullet_speed
            bullets.append(Bullet(bx, by, vx, vy, w.damage, w.color,
                                  owner="player", size=4 if w.name != "Sniper" else 5,
                                  max_dist=w.range))
        particles.burst_spark(bx, by, w.color, base_angle=self.aim_angle)
        self.recoil_offset = min(12, self.recoil_offset + w.recoil)
        self.muzzle_flash = 0.06
        camera.shake(w.recoil * 0.6)
        # Ses
        if w.sound == "pistol":
            sound_engine.shoot_pistol()
        elif w.sound == "smg":
            sound_engine.shoot_smg()
        elif w.sound == "shotgun":
            sound_engine.shoot_shotgun()
        elif w.sound == "sniper":
            sound_engine.shoot_sniper()

    def draw(self, surf, camera):
        sx, sy = camera.world_to_screen(self.x, self.y)
        # Gölge
        shadow = pygame.Surface((self.r * 3, self.r * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 90),
                            (0, 0, self.r * 3, self.r * 2))
        surf.blit(shadow, (sx - self.r * 1.5, sy - self.r * 0.6))

        # Yanıp sönme (invuln)
        if self.invuln > 0 and int(self.invuln * 20) % 2 == 0:
            body_color = C_WHITE
        else:
            body_color = C_NEON_CYAN if self.alive else (80, 80, 80)

        # Gövde
        pygame.draw.circle(surf, body_color, (int(sx), int(sy)), self.r)
        pygame.draw.circle(surf, C_BG_DARK, (int(sx), int(sy)), self.r, 3)

        # Yön göstergesi (silah)
        recoil_pull = -self.recoil_offset
        gun_len = 26 + recoil_pull
        gx = sx + math.cos(self.aim_angle) * (self.r + gun_len * 0.5)
        gy = sy + math.sin(self.aim_angle) * (self.r + gun_len * 0.5)
        # silah gövdesi
        gun_w = 8
        cos_a = math.cos(self.aim_angle)
        sin_a = math.sin(self.aim_angle)
        p1 = (sx + cos_a * (self.r - 2) - sin_a * gun_w / 2,
              sy + sin_a * (self.r - 2) + cos_a * gun_w / 2)
        p2 = (sx + cos_a * (self.r + gun_len) - sin_a * gun_w / 2,
              sy + sin_a * (self.r + gun_len) + cos_a * gun_w / 2)
        p3 = (sx + cos_a * (self.r + gun_len) + sin_a * gun_w / 2,
              sy + sin_a * (self.r + gun_len) - cos_a * gun_w / 2)
        p4 = (sx + cos_a * (self.r - 2) + sin_a * gun_w / 2,
              sy + sin_a * (self.r - 2) - cos_a * gun_w / 2)
        pygame.draw.polygon(surf, (40, 50, 70), [p1, p2, p3, p4])
        pygame.draw.polygon(surf, C_BG_DARK, [p1, p2, p3, p4], 2)

        # Muzzle flash
        if self.muzzle_flash > 0:
            mfx = sx + cos_a * (self.r + gun_len + 4)
            mfy = sy + sin_a * (self.r + gun_len + 4)
            flash = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.circle(flash, with_alpha(C_NEON_YELLOW, 200), (20, 20), 14)
            pygame.draw.circle(flash, with_alpha(C_WHITE, 220), (20, 20), 7)
            surf.blit(flash, (mfx - 20, mfy - 20),
                      special_flags=pygame.BLEND_PREMULTIPLIED)

        # Göz / yön çizgisi
        eye_x = sx + cos_a * 7
        eye_y = sy + sin_a * 7
        pygame.draw.circle(surf, C_BG_DARK, (int(eye_x), int(eye_y)), 4)

        # HP bar (ufak, baş üstü)
        if self.alive and self.hp < self.max_hp:
            bw = 40
            bh = 5
            bx = sx - bw / 2
            by = sy - self.r - 14
            pygame.draw.rect(surf, (30, 30, 40), (bx - 1, by - 1, bw + 2, bh + 2))
            ratio = self.hp / self.max_hp
            col = lerp_color(C_NEON_RED, C_NEON_GREEN, ratio)
            pygame.draw.rect(surf, col, (bx, by, bw * ratio, bh))

        # Damage flash overlay (ekran)
        # (HUD katmanında çiziliyor; oyuncu üzerinde değil)


# ============================================================================
# BÖLÜM 9: DÜŞMANLAR
# ============================================================================

class Enemy:
    """Temel düşman sınıfı."""

    KIND_GRUNT  = "grunt"
    KIND_RUNNER = "runner"
    KIND_TANK   = "tank"
    KIND_SHOOTER = "shooter"
    KIND_BOMBER = "bomber"
    KIND_BOSS   = "boss"

    def __init__(self, x, y, kind):
        self.x = x
        self.y = y
        self.kind = kind
        self.vx = 0
        self.vy = 0
        self.alive = True
        self.hit_flash = 0.0
        self.attack_cd = 0.0
        self.angle = 0.0
        self.anim = random.uniform(0, 6.28)
        self._configure(kind)

    def _configure(self, kind):
        if kind == self.KIND_GRUNT:
            self.r = 18
            self.hp = 50
            self.speed = 110
            self.damage = 12
            self.color = C_NEON_PINK
            self.gold = 5
            self.xp = 10
            self.touch = True
        elif kind == self.KIND_RUNNER:
            self.r = 14
            self.hp = 30
            self.speed = 220
            self.damage = 8
            self.color = C_NEON_YELLOW
            self.gold = 7
            self.xp = 12
            self.touch = True
        elif kind == self.KIND_TANK:
            self.r = 28
            self.hp = 220
            self.speed = 70
            self.damage = 22
            self.color = C_NEON_PURPLE
            self.gold = 18
            self.xp = 30
            self.touch = True
        elif kind == self.KIND_SHOOTER:
            self.r = 16
            self.hp = 60
            self.speed = 80
            self.damage = 10
            self.color = C_NEON_GREEN
            self.gold = 12
            self.xp = 18
            self.touch = False
            self.shoot_range = 380
            self.shoot_cd = 0.0
            self.shoot_interval = 1.5
        elif kind == self.KIND_BOMBER:
            self.r = 17
            self.hp = 40
            self.speed = 160
            self.damage = 40
            self.color = C_NEON_ORANGE
            self.gold = 15
            self.xp = 22
            self.touch = True
            self.explode_range = 60
        elif kind == self.KIND_BOSS:
            self.r = 56
            self.hp = 2200
            self.speed = 90
            self.damage = 35
            self.color = C_NEON_RED
            self.gold = 250
            self.xp = 400
            self.touch = True
            self.shoot_cd = 0.0
            self.shoot_interval = 0.7
            self.shoot_range = 700
        self.max_hp = self.hp

    def take_damage(self, dmg, particles=None):
        self.hp -= dmg
        self.hit_flash = 0.12
        if particles:
            particles.burst_blood(self.x, self.y, color=self.color)
        if self.hp <= 0:
            self.alive = False

    def update(self, dt, player, bullets, particles, sound_engine):
        if not self.alive:
            return
        self.anim += dt * 4
        if self.hit_flash > 0:
            self.hit_flash -= dt
        d = dist((self.x, self.y), (player.x, player.y))
        ang = math.atan2(player.y - self.y, player.x - self.x)
        self.angle = ang
        if self.touch:
            # Player'a yaklaş
            target_d = self.r + player.r
            if d > target_d - 2:
                self.x += math.cos(ang) * self.speed * dt
                self.y += math.sin(ang) * self.speed * dt
            else:
                # Saldırı (temas)
                if self.kind == self.KIND_BOMBER:
                    # Patla
                    particles.burst_explosion(self.x, self.y)
                    sound_engine.explosion()
                    if d < self.explode_range + player.r:
                        player.take_damage(self.damage, sound_engine)
                    self.alive = False
                else:
                    self.attack_cd -= dt
                    if self.attack_cd <= 0:
                        player.take_damage(self.damage, sound_engine)
                        self.attack_cd = 0.7
        else:
            # Mesafeli düşman: range içinde dur ve ateş et
            target_d = self.shoot_range * 0.7
            if d > self.shoot_range:
                self.x += math.cos(ang) * self.speed * dt
                self.y += math.sin(ang) * self.speed * dt
            elif d < self.shoot_range * 0.5:
                self.x -= math.cos(ang) * self.speed * 0.6 * dt
                self.y -= math.sin(ang) * self.speed * 0.6 * dt
            self.shoot_cd -= dt
            if self.shoot_cd <= 0 and d < self.shoot_range:
                self.shoot_cd = self.shoot_interval
                bspeed = 600
                vx = math.cos(ang) * bspeed
                vy = math.sin(ang) * bspeed
                bullets.append(Bullet(self.x + math.cos(ang) * (self.r + 6),
                                      self.y + math.sin(ang) * (self.r + 6),
                                      vx, vy, self.damage,
                                      self.color, owner="enemy",
                                      size=5, max_dist=900))

        # Boss özel: çevreye sürekli ateş
        if self.kind == self.KIND_BOSS:
            self.shoot_cd -= dt
            if self.shoot_cd <= 0:
                self.shoot_cd = self.shoot_interval
                # 6 yönlü dağılım
                base = ang
                for i in range(6):
                    a = base + (i - 2.5) * 0.18
                    vx = math.cos(a) * 520
                    vy = math.sin(a) * 520
                    bullets.append(Bullet(self.x + math.cos(a) * (self.r + 6),
                                          self.y + math.sin(a) * (self.r + 6),
                                          vx, vy, self.damage * 0.5,
                                          self.color, owner="enemy",
                                          size=6, max_dist=1100))

        # Sınırlar
        self.x = clamp(self.x, self.r, WORLD_WIDTH - self.r)
        self.y = clamp(self.y, self.r, WORLD_HEIGHT - self.r)

    def draw(self, surf, camera):
        if not self.alive:
            return
        sx, sy = camera.world_to_screen(self.x, self.y)
        if sx < -60 or sy < -60 or sx > camera.w + 60 or sy > camera.h + 60:
            return
        # Gölge
        shadow = pygame.Surface((self.r * 3, self.r * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 90),
                            (0, 0, self.r * 3, self.r * 2))
        surf.blit(shadow, (sx - self.r * 1.5, sy - self.r * 0.6))

        col = self.color if self.hit_flash <= 0 else C_WHITE
        # Pulse
        pulse = 1.0 + math.sin(self.anim) * 0.05

        if self.kind == Enemy.KIND_GRUNT:
            r = int(self.r * pulse)
            pygame.draw.circle(surf, col, (int(sx), int(sy)), r)
            pygame.draw.circle(surf, C_BG_DARK, (int(sx), int(sy)), r, 2)
            # gözler
            ex = math.cos(self.angle) * 6
            ey = math.sin(self.angle) * 6
            pygame.draw.circle(surf, C_BG_DARK, (int(sx + ex), int(sy + ey)), 3)

        elif self.kind == Enemy.KIND_RUNNER:
            # Üçgen
            pts = []
            for i in range(3):
                a = self.angle + i * 2.094
                pts.append((sx + math.cos(a) * self.r * 1.4,
                            sy + math.sin(a) * self.r * 1.4))
            pygame.draw.polygon(surf, col, pts)
            pygame.draw.polygon(surf, C_BG_DARK, pts, 2)

        elif self.kind == Enemy.KIND_TANK:
            # Kare gövde
            size = self.r * 1.6
            rect = pygame.Rect(sx - size / 2, sy - size / 2, size, size)
            pygame.draw.rect(surf, col, rect, border_radius=6)
            pygame.draw.rect(surf, C_BG_DARK, rect, 3, border_radius=6)
            # iç parça
            pygame.draw.circle(surf, C_BG_DARK, (int(sx), int(sy)), 6)

        elif self.kind == Enemy.KIND_SHOOTER:
            r = int(self.r * pulse)
            pygame.draw.circle(surf, col, (int(sx), int(sy)), r)
            pygame.draw.circle(surf, C_BG_DARK, (int(sx), int(sy)), r, 2)
            # namlu
            tx = sx + math.cos(self.angle) * (r + 10)
            ty = sy + math.sin(self.angle) * (r + 10)
            pygame.draw.line(surf, C_BG_DARK, (sx, sy), (tx, ty), 4)

        elif self.kind == Enemy.KIND_BOMBER:
            r = int(self.r * pulse)
            pygame.draw.circle(surf, col, (int(sx), int(sy)), r)
            # ikaz şeritleri
            for k in range(0, 360, 60):
                a = math.radians(k + self.anim * 30)
                x1 = sx + math.cos(a) * (r - 4)
                y1 = sy + math.sin(a) * (r - 4)
                x2 = sx + math.cos(a) * (r + 2)
                y2 = sy + math.sin(a) * (r + 2)
                pygame.draw.line(surf, C_BG_DARK, (x1, y1), (x2, y2), 3)

        elif self.kind == Enemy.KIND_BOSS:
            r = int(self.r * pulse)
            # Dış halka
            pygame.draw.circle(surf, col, (int(sx), int(sy)), r)
            pygame.draw.circle(surf, C_BG_DARK, (int(sx), int(sy)), r, 4)
            # iç çark
            for k in range(0, 360, 45):
                a = math.radians(k) + self.anim
                x = sx + math.cos(a) * (r - 8)
                y = sy + math.sin(a) * (r - 8)
                pygame.draw.circle(surf, C_BG_DARK, (int(x), int(y)), 5)
            # göz
            pygame.draw.circle(surf, C_WHITE, (int(sx), int(sy)), 12)
            pygame.draw.circle(surf, C_BG_DARK, (int(sx + math.cos(self.angle) * 4),
                                                 int(sy + math.sin(self.angle) * 4)), 6)

        # HP barı (boss hariç ekranda da)
        if self.kind != Enemy.KIND_BOSS:
            bw = self.r * 2
            bh = 4
            bx = sx - bw / 2
            by = sy - self.r - 10
            pygame.draw.rect(surf, (30, 30, 40), (bx - 1, by - 1, bw + 2, bh + 2))
            ratio = max(0.0, self.hp / self.max_hp)
            cc = lerp_color(C_NEON_RED, C_NEON_GREEN, ratio)
            pygame.draw.rect(surf, cc, (bx, by, bw * ratio, bh))


# ============================================================================
# BÖLÜM 10: PICKUP / TOPLANABİLİRLER
# ============================================================================

class Pickup:
    KIND_HP    = "hp"
    KIND_ARMOR = "armor"
    KIND_AMMO  = "ammo"
    KIND_GOLD  = "gold"

    def __init__(self, x, y, kind, value):
        self.x = x
        self.y = y
        self.kind = kind
        self.value = value
        self.r = 12
        self.life = 25.0
        self.bob = random.uniform(0, 6.28)
        self.alive = True

    def update(self, dt, player, sound_engine):
        if not self.alive:
            return
        self.bob += dt * 4
        self.life -= dt
        if self.life <= 0:
            self.alive = False
            return
        if dist((self.x, self.y), (player.x, player.y)) < self.r + player.r:
            self.apply(player, sound_engine)
            self.alive = False

    def apply(self, player, sound_engine):
        if self.kind == Pickup.KIND_HP:
            player.heal(self.value)
        elif self.kind == Pickup.KIND_ARMOR:
            player.add_armor(self.value)
        elif self.kind == Pickup.KIND_AMMO:
            for w in player.weapons:
                w.add_ammo(self.value)
        elif self.kind == Pickup.KIND_GOLD:
            player.gold += self.value
        sound_engine.pickup()

    def draw(self, surf, camera):
        if not self.alive:
            return
        sx, sy = camera.world_to_screen(self.x, self.y)
        oy = math.sin(self.bob) * 3
        if self.kind == Pickup.KIND_HP:
            col = C_NEON_GREEN
            pygame.draw.rect(surf, col, (sx - 8, sy - 3 + oy, 16, 6))
            pygame.draw.rect(surf, col, (sx - 3, sy - 8 + oy, 6, 16))
        elif self.kind == Pickup.KIND_ARMOR:
            col = C_NEON_CYAN
            pts = [(sx, sy - 10 + oy), (sx + 9, sy - 2 + oy),
                   (sx + 5, sy + 9 + oy), (sx - 5, sy + 9 + oy),
                   (sx - 9, sy - 2 + oy)]
            pygame.draw.polygon(surf, col, pts)
            pygame.draw.polygon(surf, C_BG_DARK, pts, 2)
        elif self.kind == Pickup.KIND_AMMO:
            col = C_NEON_YELLOW
            pygame.draw.rect(surf, col, (sx - 6, sy - 9 + oy, 12, 18), border_radius=2)
            pygame.draw.rect(surf, C_BG_DARK, (sx - 6, sy - 9 + oy, 12, 18), 2, border_radius=2)
        elif self.kind == Pickup.KIND_GOLD:
            col = (255, 200, 60)
            pygame.draw.circle(surf, col, (int(sx), int(sy + oy)), 9)
            pygame.draw.circle(surf, C_BG_DARK, (int(sx), int(sy + oy)), 9, 2)


# ============================================================================
# BÖLÜM 11: WAVE (DALGA) MOTORU
# ============================================================================

class WaveManager:
    def __init__(self):
        self.wave = 0
        self.in_wave = False
        self.spawn_queue = []
        self.spawn_timer = 0.0
        self.intermission = 4.0
        self.inter_t = 3.0
        self.completed = False

    def start_next_wave(self, sound_engine):
        self.wave += 1
        self.in_wave = True
        self.spawn_queue = self._compose_wave(self.wave)
        self.spawn_timer = 0.0
        sound_engine.wave_start()

    def _compose_wave(self, w):
        """Dalgayı oluşturan düşman listesi."""
        q = []
        # Temel grunt sayısı
        n_grunt = 4 + w * 2
        for _ in range(n_grunt):
            q.append(Enemy.KIND_GRUNT)
        # Runner: 2. dalgadan
        if w >= 2:
            for _ in range(2 + w):
                q.append(Enemy.KIND_RUNNER)
        # Shooter: 3. dalgadan
        if w >= 3:
            for _ in range(1 + w // 2):
                q.append(Enemy.KIND_SHOOTER)
        # Bomber: 4. dalgadan
        if w >= 4:
            for _ in range(1 + w // 3):
                q.append(Enemy.KIND_BOMBER)
        # Tank: 5. dalgadan
        if w >= 5:
            for _ in range(1 + w // 4):
                q.append(Enemy.KIND_TANK)
        # Boss: her 5 dalgada
        if w % 5 == 0:
            q.append(Enemy.KIND_BOSS)
        random.shuffle(q)
        return q

    def update(self, dt, enemies, player, sound_engine):
        if not self.in_wave:
            self.inter_t -= dt
            if self.inter_t <= 0:
                self.start_next_wave(sound_engine)
            return
        # Spawn
        if self.spawn_queue:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                kind = self.spawn_queue.pop()
                e = self._spawn_enemy(kind, player)
                enemies.append(e)
                self.spawn_timer = random.uniform(0.25, 0.8)
                if kind == Enemy.KIND_BOSS:
                    self.spawn_timer = 1.5
        else:
            # Tüm düşmanlar öldü mü?
            if not any(e.alive for e in enemies):
                self.in_wave = False
                self.inter_t = self.intermission

    def _spawn_enemy(self, kind, player):
        # Oyuncudan uzakta ve ekran dışında doğur
        for _ in range(60):
            x = random.uniform(40, WORLD_WIDTH - 40)
            y = random.uniform(40, WORLD_HEIGHT - 40)
            if dist((x, y), (player.x, player.y)) > 360:
                return Enemy(x, y, kind)
        return Enemy(40, 40, kind)


# ============================================================================
# BÖLÜM 12: HUD VE UI BİLEŞENLERİ
# ============================================================================

class Button:
    def __init__(self, rect, label, on_click=None, color=C_NEON_CYAN):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.color = color
        self.hover = False

    def update(self, mpos):
        self.hover = self.rect.collidepoint(mpos)

    def draw(self, surf, font):
        bg = (30, 35, 55) if not self.hover else (50, 60, 90)
        pygame.draw.rect(surf, bg, self.rect, border_radius=8)
        pygame.draw.rect(surf, self.color, self.rect, 2, border_radius=8)
        txt = font.render(self.label, True, C_WHITE)
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def click(self, mpos, sound_engine=None):
        if self.rect.collidepoint(mpos):
            if sound_engine:
                sound_engine.click()
            if self.on_click:
                self.on_click()
            return True
        return False


def draw_text(surf, text, font, color, x, y, center=False, shadow=True):
    if shadow:
        sh = font.render(text, True, (0, 0, 0))
        srect = sh.get_rect()
        if center:
            srect.center = (x + 2, y + 2)
        else:
            srect.topleft = (x + 2, y + 2)
        surf.blit(sh, srect)
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    surf.blit(img, rect)


def draw_bar(surf, x, y, w, h, ratio, color, bg=(30, 30, 45), border=C_HUD_BORDER):
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=4)
    inner = max(0, int(w * clamp(ratio, 0, 1)))
    if inner > 0:
        pygame.draw.rect(surf, color, (x, y, inner, h), border_radius=4)
    pygame.draw.rect(surf, border, (x, y, w, h), 2, border_radius=4)


# ============================================================================
# BÖLÜM 13: ARKAPLAN GRID ÇİZİMİ
# ============================================================================

def draw_background(surf, camera):
    surf.fill(C_BG_DARK)
    grid = 80
    sx = -int(camera.x) % grid
    sy = -int(camera.y) % grid
    w = camera.w
    h = camera.h
    # ince çizgiler
    for x in range(sx, w, grid):
        pygame.draw.line(surf, C_BG_GRID, (x, 0), (x, h), 1)
    for y in range(sy, h, grid):
        pygame.draw.line(surf, C_BG_GRID, (0, y), (w, y), 1)
    # büyük çizgiler
    big = grid * 4
    bsx = -int(camera.x) % big
    bsy = -int(camera.y) % big
    for x in range(bsx, w, big):
        pygame.draw.line(surf, C_BG_GRID_BRIGHT, (x, 0), (x, h), 2)
    for y in range(bsy, h, big):
        pygame.draw.line(surf, C_BG_GRID_BRIGHT, (0, y), (w, y), 2)
    # vinyet köşeler
    vignette = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(vignette, (0, 0, 0, 120), (0, 0, w, h), 80)
    surf.blit(vignette, (0, 0))


def draw_world_bounds(surf, camera):
    x, y = camera.world_to_screen(0, 0)
    pygame.draw.rect(surf, C_NEON_PINK,
                     (x, y, WORLD_WIDTH, WORLD_HEIGHT), 4)


# ============================================================================
# BÖLÜM 14: HASAR YAZILARI (Damage Numbers)
# ============================================================================

class FloatingText:
    __slots__ = ("x", "y", "vy", "text", "color", "life", "max_life", "size")

    def __init__(self, x, y, text, color, size=20):
        self.x = x
        self.y = y
        self.vy = -50
        self.text = text
        self.color = color
        self.life = 0.8
        self.max_life = 0.8
        self.size = size

    def update(self, dt):
        self.y += self.vy * dt
        self.vy += 60 * dt
        self.life -= dt
        return self.life > 0

    def draw(self, surf, camera, font):
        sx, sy = camera.world_to_screen(self.x, self.y)
        t = clamp(self.life / self.max_life, 0, 1)
        col = (self.color[0], self.color[1], self.color[2])
        img = font.render(self.text, True, col)
        img.set_alpha(int(255 * t))
        surf.blit(img, img.get_rect(center=(sx, sy)))


# ============================================================================
# BÖLÜM 15: ANA OYUN SINIFI
# ============================================================================

class Game:
    STATE_MENU       = "menu"
    STATE_PLAYING    = "playing"
    STATE_PAUSED     = "paused"
    STATE_GAMEOVER   = "gameover"
    STATE_OPTIONS    = "options"
    STATE_HOWTO      = "howto"

    def __init__(self):
        pygame.init()
        pygame.display.set_caption(GAME_TITLE)
        self.fullscreen = True
        self.flags = pygame.FULLSCREEN | pygame.SCALED | pygame.DOUBLEBUF
        info = pygame.display.Info()
        self.w = info.current_w
        self.h = info.current_h
        try:
            self.screen = pygame.display.set_mode((self.w, self.h), self.flags)
        except Exception:
            self.fullscreen = False
            self.flags = pygame.RESIZABLE | pygame.DOUBLEBUF
            self.w, self.h = DEFAULT_WIDTH, DEFAULT_HEIGHT
            self.screen = pygame.display.set_mode((self.w, self.h), self.flags)
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = Game.STATE_MENU
        self.show_fps = False

        # Fontlar (sistem fontu)
        self.font_xs = pygame.font.SysFont("consolas,arial", 14, bold=True)
        self.font_sm = pygame.font.SysFont("consolas,arial", 18, bold=True)
        self.font_md = pygame.font.SysFont("consolas,arial", 26, bold=True)
        self.font_lg = pygame.font.SysFont("consolas,arial", 44, bold=True)
        self.font_xl = pygame.font.SysFont("consolas,arial", 84, bold=True)

        self.sound = SoundEngine()
        self.high_score = 0
        self.load_save()

        # Menü butonları
        self._build_menus()

        # Oyun durumu
        self._init_game_state()

        # Kursör gizle (custom crosshair)
        pygame.mouse.set_visible(False)

    # ---- yardımcı: cursor / fullscreen ----------------------------------
    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            info = pygame.display.Info()
            self.w = info.current_w
            self.h = info.current_h
            self.screen = pygame.display.set_mode(
                (self.w, self.h),
                pygame.FULLSCREEN | pygame.SCALED | pygame.DOUBLEBUF
            )
        else:
            self.w, self.h = DEFAULT_WIDTH, DEFAULT_HEIGHT
            self.screen = pygame.display.set_mode(
                (self.w, self.h),
                pygame.RESIZABLE | pygame.DOUBLEBUF
            )
        if hasattr(self, "camera"):
            self.camera.resize(self.w, self.h)
        self._build_menus()

    # ---- menü ----------------------------------------------------------
    def _build_menus(self):
        cx = self.w // 2
        cy = self.h // 2
        bw, bh = 280, 56
        self.menu_buttons = [
            Button((cx - bw // 2, cy - 40,  bw, bh), "OYUNA BAŞLA", self.start_game, C_NEON_CYAN),
            Button((cx - bw // 2, cy + 30,  bw, bh), "NASIL OYNANIR", lambda: self._set_state(Game.STATE_HOWTO), C_NEON_GREEN),
            Button((cx - bw // 2, cy + 100, bw, bh), "AYARLAR",    lambda: self._set_state(Game.STATE_OPTIONS), C_NEON_PURPLE),
            Button((cx - bw // 2, cy + 170, bw, bh), "ÇIKIŞ",      self._quit, C_NEON_RED),
        ]
        self.pause_buttons = [
            Button((cx - bw // 2, cy - 30, bw, bh), "DEVAM ET", self.resume, C_NEON_GREEN),
            Button((cx - bw // 2, cy + 40, bw, bh), "ANA MENÜ",  self.to_menu, C_NEON_YELLOW),
            Button((cx - bw // 2, cy + 110, bw, bh), "ÇIKIŞ",    self._quit, C_NEON_RED),
        ]
        self.gameover_buttons = [
            Button((cx - bw // 2, cy + 60, bw, bh), "TEKRAR DENE", self.start_game, C_NEON_CYAN),
            Button((cx - bw // 2, cy + 130, bw, bh), "ANA MENÜ",   self.to_menu, C_NEON_YELLOW),
        ]
        self.options_buttons = [
            Button((cx - bw // 2, cy - 30, bw, bh), "TAM EKRAN: AÇ/KAPA", self.toggle_fullscreen, C_NEON_CYAN),
            Button((cx - bw // 2, cy + 40, bw, bh), "SES: " + ("AÇIK" if self.sound.enabled else "KAPALI"),
                   self._toggle_sound, C_NEON_GREEN),
            Button((cx - bw // 2, cy + 110, bw, bh), "GERİ", lambda: self._set_state(Game.STATE_MENU), C_NEON_YELLOW),
        ]
        self.howto_buttons = [
            Button((cx - bw // 2, cy + 230, bw, bh), "GERİ", lambda: self._set_state(Game.STATE_MENU), C_NEON_YELLOW),
        ]

    def _toggle_sound(self):
        self.sound.enabled = not self.sound.enabled
        self._build_menus()

    def _set_state(self, s):
        self.state = s
        self._build_menus()

    def _quit(self):
        self.running = False

    # ---- save / load ---------------------------------------------------
    def load_save(self):
        try:
            if os.path.exists(SAVE_FILE):
                with open(SAVE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.high_score = int(data.get("high_score", 0))
        except Exception:
            self.high_score = 0

    def save(self):
        try:
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump({"high_score": self.high_score,
                           "version": GAME_VERSION}, f)
        except Exception:
            pass

    # ---- oyun init -----------------------------------------------------
    def _init_game_state(self):
        self.camera = Camera(self.w, self.h)
        self.player = Player(WORLD_WIDTH / 2, WORLD_HEIGHT / 2)
        self.bullets = []
        self.enemies = []
        self.pickups = []
        self.particles = ParticleSystem()
        self.floats = []
        self.waves = WaveManager()
        self.elapsed = 0.0
        self.firing = False

    def start_game(self):
        self._init_game_state()
        self.state = Game.STATE_PLAYING

    def resume(self):
        if self.state == Game.STATE_PAUSED:
            self.state = Game.STATE_PLAYING

    def to_menu(self):
        self.state = Game.STATE_MENU

    # ---- ana döngü -----------------------------------------------------
    def run(self):
        while self.running:
            dt = min(self.clock.tick(TARGET_FPS) / 1000.0, 1 / 30.0)
            self.handle_events()
            if self.state == Game.STATE_PLAYING:
                self.update(dt)
            self.render()
        self.save()
        pygame.quit()

    # ---- olaylar -------------------------------------------------------
    def handle_events(self):
        mpos = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.VIDEORESIZE and not self.fullscreen:
                self.w, self.h = ev.w, ev.h
                self.screen = pygame.display.set_mode((self.w, self.h), self.flags)
                self.camera.resize(self.w, self.h)
                self._build_menus()
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_F11:
                    self.toggle_fullscreen()
                elif ev.key == pygame.K_F1:
                    self.show_fps = not self.show_fps
                elif ev.key == pygame.K_ESCAPE:
                    if self.state == Game.STATE_PLAYING:
                        self.state = Game.STATE_PAUSED
                    elif self.state == Game.STATE_PAUSED:
                        self.state = Game.STATE_PLAYING
                    elif self.state in (Game.STATE_OPTIONS, Game.STATE_HOWTO):
                        self.state = Game.STATE_MENU
                if self.state == Game.STATE_PLAYING and self.player.alive:
                    if ev.key == pygame.K_r:
                        self.player.weapon.reload(self.sound)
                    elif ev.key == pygame.K_SPACE:
                        keys = pygame.key.get_pressed()
                        dx = (1 if keys[pygame.K_d] else 0) - (1 if keys[pygame.K_a] else 0)
                        dy = (1 if keys[pygame.K_s] else 0) - (1 if keys[pygame.K_w] else 0)
                        self.player.start_dash(dx, dy)
                    else:
                        for i, w in enumerate(self.player.weapons):
                            if ev.key == w.key:
                                self.player.switch_weapon(i, self.sound)
                                break
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    if self.state == Game.STATE_MENU:
                        for b in self.menu_buttons:
                            b.click(mpos, self.sound)
                    elif self.state == Game.STATE_PAUSED:
                        for b in self.pause_buttons:
                            b.click(mpos, self.sound)
                    elif self.state == Game.STATE_GAMEOVER:
                        for b in self.gameover_buttons:
                            b.click(mpos, self.sound)
                    elif self.state == Game.STATE_OPTIONS:
                        for b in self.options_buttons:
                            b.click(mpos, self.sound)
                    elif self.state == Game.STATE_HOWTO:
                        for b in self.howto_buttons:
                            b.click(mpos, self.sound)
                    elif self.state == Game.STATE_PLAYING:
                        self.firing = True
            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button == 1:
                    self.firing = False

        # Hover update
        if self.state == Game.STATE_MENU:
            for b in self.menu_buttons:
                b.update(mpos)
        elif self.state == Game.STATE_PAUSED:
            for b in self.pause_buttons:
                b.update(mpos)
        elif self.state == Game.STATE_GAMEOVER:
            for b in self.gameover_buttons:
                b.update(mpos)
        elif self.state == Game.STATE_OPTIONS:
            for b in self.options_buttons:
                b.update(mpos)
        elif self.state == Game.STATE_HOWTO:
            for b in self.howto_buttons:
                b.update(mpos)

    # ---- güncelleme ----------------------------------------------------
    def update(self, dt):
        self.elapsed += dt
        keys = pygame.key.get_pressed()
        mpos = pygame.mouse.get_pos()
        mouse_world = self.camera.screen_to_world(*mpos)

        # Player
        self.player.update(dt, keys, mouse_world, self.sound)

        # Otomatik / yarı otomatik ateş
        if self.player.alive and self.firing:
            w = self.player.weapon
            if w.full_auto or self._fire_edge:
                self.player.fire(self.bullets, self.particles, self.camera, self.sound)
            self._fire_edge = False
        else:
            self._fire_edge = True

        # Mouse down'a tek atışta tetiklemek için: yarı otomatik için
        # _fire_edge basıldığı an False olur, butonu bırakınca True'ya döner
        if not self.firing:
            self._fire_edge = True

        # Kamera
        self.camera.follow(self.player.x, self.player.y, dt)

        # Wave
        self.waves.update(dt, self.enemies, self.player, self.sound)

        # Düşmanlar
        for e in self.enemies:
            e.update(dt, self.player, self.bullets, self.particles, self.sound)

        # Mermiler
        new_bullets = []
        for b in self.bullets:
            if not b.update(dt):
                continue
            hit = False
            if b.owner == "player":
                # düşmanlara çarp
                for e in self.enemies:
                    if not e.alive:
                        continue
                    if dist_sq((b.x, b.y), (e.x, e.y)) < (e.r + b.size) ** 2:
                        e.take_damage(b.damage, self.particles)
                        self.floats.append(FloatingText(e.x, e.y - e.r - 6,
                                                        f"-{int(b.damage)}",
                                                        C_NEON_YELLOW, 18))
                        self.sound.hit()
                        hit = True
                        if not e.alive:
                            self._on_enemy_killed(e)
                        break
            else:
                # oyuncuya çarp
                if self.player.alive and dist_sq((b.x, b.y), (self.player.x, self.player.y)) < (self.player.r + b.size) ** 2:
                    self.player.take_damage(b.damage, self.sound)
                    hit = True
            if not hit:
                new_bullets.append(b)
        self.bullets = new_bullets

        # Pickups
        for p in self.pickups:
            p.update(dt, self.player, self.sound)
        self.pickups = [p for p in self.pickups if p.alive]

        # Ölü düşmanları temizle
        self.enemies = [e for e in self.enemies if e.alive]

        # Partiküller / floating text
        self.particles.update(dt)
        self.floats = [f for f in self.floats if f.update(dt)]

        # Game Over
        if not self.player.alive:
            self.state = Game.STATE_GAMEOVER
            if self.player.score > self.high_score:
                self.high_score = self.player.score
                self.save()

    def _on_enemy_killed(self, e):
        self.player.score += int(e.xp)
        self.player.gold += e.gold
        self.player.kills += 1
        self.particles.burst_explosion(e.x, e.y) if e.kind == Enemy.KIND_BOSS else self.particles.burst_blood(e.x, e.y, e.color)
        if e.kind == Enemy.KIND_BOMBER:
            # Bomber zaten patlıyor; ama yine ekstra
            self.particles.burst_explosion(e.x, e.y)
            self.sound.explosion()
            self.camera.shake(12)
        if e.kind == Enemy.KIND_BOSS:
            self.camera.shake(28)
        # Drop
        roll = random.random()
        if e.kind == Enemy.KIND_BOSS:
            self._drop(e.x, e.y, Pickup.KIND_HP, 60)
            self._drop(e.x + 20, e.y, Pickup.KIND_ARMOR, 60)
            self._drop(e.x - 20, e.y, Pickup.KIND_AMMO, 80)
            self._drop(e.x, e.y + 24, Pickup.KIND_GOLD, 120)
        elif roll < 0.10:
            self._drop(e.x, e.y, Pickup.KIND_HP, 25)
        elif roll < 0.18:
            self._drop(e.x, e.y, Pickup.KIND_ARMOR, 25)
        elif roll < 0.40:
            self._drop(e.x, e.y, Pickup.KIND_AMMO, 30)
        elif roll < 0.55:
            self._drop(e.x, e.y, Pickup.KIND_GOLD, 10)

    def _drop(self, x, y, kind, value):
        self.pickups.append(Pickup(x, y, kind, value))

    # ---- render -------------------------------------------------------
    def render(self):
        if self.state == Game.STATE_MENU:
            self._render_menu()
        elif self.state == Game.STATE_PLAYING:
            self._render_game()
            self._render_hud()
        elif self.state == Game.STATE_PAUSED:
            self._render_game()
            self._render_hud()
            self._render_pause_overlay()
        elif self.state == Game.STATE_GAMEOVER:
            self._render_game()
            self._render_hud()
            self._render_gameover_overlay()
        elif self.state == Game.STATE_OPTIONS:
            self._render_options()
        elif self.state == Game.STATE_HOWTO:
            self._render_howto()
        self._render_cursor()
        if self.show_fps:
            fps = self.clock.get_fps()
            draw_text(self.screen, f"FPS {fps:.0f}", self.font_sm,
                      C_NEON_YELLOW, 10, 10)
        pygame.display.flip()

    # ---- ana menü ekranı ----------------------------------------------
    def _render_menu(self):
        self.screen.fill(C_BG_DARK)
        # Animasyonlu arka plan grid
        t = pygame.time.get_ticks() / 1000.0
        ox = int(math.sin(t * 0.3) * 60)
        oy = int(math.cos(t * 0.4) * 40)
        for x in range(-200 + ox % 80, self.w, 80):
            pygame.draw.line(self.screen, C_BG_GRID, (x, 0), (x, self.h), 1)
        for y in range(-200 + oy % 80, self.h, 80):
            pygame.draw.line(self.screen, C_BG_GRID, (0, y), (self.w, y), 1)

        # Başlık
        title = GAME_TITLE
        glow = self.font_xl.render(title, True, C_NEON_PINK)
        glow.set_alpha(110)
        for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3)]:
            self.screen.blit(glow, glow.get_rect(center=(self.w // 2 + dx,
                                                          self.h // 2 - 200 + dy)))
        draw_text(self.screen, title, self.font_xl, C_NEON_CYAN,
                  self.w // 2, self.h // 2 - 200, center=True)
        draw_text(self.screen, "Top-Down Arena Shooter", self.font_md,
                  C_HUD_DIM, self.w // 2, self.h // 2 - 140, center=True)

        # En yüksek skor
        draw_text(self.screen, f"EN YÜKSEK SKOR: {self.high_score}",
                  self.font_sm, C_NEON_YELLOW,
                  self.w // 2, self.h // 2 - 90, center=True)

        for b in self.menu_buttons:
            b.draw(self.screen, self.font_sm)

        draw_text(self.screen, f"v{GAME_VERSION}", self.font_xs,
                  C_HUD_DIM, self.w - 60, self.h - 24)
        draw_text(self.screen, "F11: Tam Ekran  |  F1: FPS", self.font_xs,
                  C_HUD_DIM, 10, self.h - 24)

    # ---- options ------------------------------------------------------
    def _render_options(self):
        self.screen.fill(C_BG_DARK)
        draw_text(self.screen, "AYARLAR", self.font_lg, C_NEON_CYAN,
                  self.w // 2, self.h // 2 - 140, center=True)
        for b in self.options_buttons:
            b.draw(self.screen, self.font_sm)

    # ---- howto --------------------------------------------------------
    def _render_howto(self):
        self.screen.fill(C_BG_DARK)
        draw_text(self.screen, "NASIL OYNANIR", self.font_lg, C_NEON_CYAN,
                  self.w // 2, 100, center=True)
        lines = [
            "WASD / Ok Tuşları : Hareket",
            "Fare              : Nişan",
            "Sol Tık           : Ateş",
            "1 - 2 - 3 - 4     : Silah Değiştir",
            "R                 : Şarjör Değiştir (Reload)",
            "Shift             : Sprint",
            "Space             : Dash (kısa atılma, geçici dokunulmazlık)",
            "ESC               : Pause / Menü",
            "F11               : Tam Ekran",
            "",
            "Düşmanları öldürerek altın & XP kazan.",
            "Yere düşen kutuları topla: HP, Zırh, Mühimmat, Altın.",
            "Her 5 dalgada bir BOSS belirir!",
        ]
        y = 180
        for line in lines:
            draw_text(self.screen, line, self.font_sm, C_WHITE,
                      self.w // 2, y, center=True)
            y += 28
        for b in self.howto_buttons:
            b.draw(self.screen, self.font_sm)

    # ---- oyun render --------------------------------------------------
    def _render_game(self):
        draw_background(self.screen, self.camera)
        draw_world_bounds(self.screen, self.camera)

        # Pickups (altta)
        for p in self.pickups:
            p.draw(self.screen, self.camera)

        # Düşmanlar
        for e in self.enemies:
            e.draw(self.screen, self.camera)

        # Player
        self.player.draw(self.screen, self.camera)

        # Mermiler
        for b in self.bullets:
            b.draw(self.screen, self.camera)

        # Partiküller
        self.particles.draw(self.screen, self.camera)

        # Floating text
        for f in self.floats:
            f.draw(self.screen, self.camera, self.font_sm)

        # Damage flash overlay
        if self.player.damage_flash > 0:
            a = int(120 * (self.player.damage_flash / 0.4))
            ov = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            ov.fill((255, 30, 30, a))
            self.screen.blit(ov, (0, 0))

        # Düşük HP vinyet
        if self.player.hp / self.player.max_hp < 0.35 and self.player.alive:
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 200.0)
            a = int(60 + 60 * pulse)
            ov = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            pygame.draw.rect(ov, (200, 0, 0, a), (0, 0, self.w, self.h), 80)
            self.screen.blit(ov, (0, 0))

    # ---- HUD ----------------------------------------------------------
    def _render_hud(self):
        # Sol alt: HP/Armor
        pad = 16
        bar_w = 320
        bar_h = 18
        x = pad
        y = self.h - pad - bar_h * 2 - 10
        # HP
        draw_bar(self.screen, x, y, bar_w, bar_h,
                 self.player.hp / self.player.max_hp, C_NEON_GREEN)
        draw_text(self.screen, f"HP {int(self.player.hp)}/{self.player.max_hp}",
                  self.font_xs, C_WHITE, x + 8, y + 2)
        # Armor
        draw_bar(self.screen, x, y + bar_h + 6, bar_w, bar_h,
                 self.player.armor / self.player.max_armor, C_NEON_CYAN)
        draw_text(self.screen, f"ZIRH {int(self.player.armor)}/{self.player.max_armor}",
                  self.font_xs, C_WHITE, x + 8, y + bar_h + 8)

        # Dash cooldown
        dx = x + bar_w + 16
        dy = y
        ratio = 1.0 - (self.player.dash_cd / DASH_COOLDOWN if self.player.dash_cd > 0 else 0)
        draw_bar(self.screen, dx, dy, 120, bar_h, ratio, C_NEON_PURPLE)
        draw_text(self.screen, "DASH", self.font_xs, C_WHITE, dx + 8, dy + 2)

        # Sağ alt: silah & mermi
        w = self.player.weapon
        wx = self.w - 320
        wy = self.h - pad - 80
        pygame.draw.rect(self.screen, C_HUD_BG, (wx, wy, 304, 76), border_radius=8)
        pygame.draw.rect(self.screen, w.color, (wx, wy, 304, 76), 2, border_radius=8)
        draw_text(self.screen, w.name.upper(), self.font_md, w.color, wx + 12, wy + 8)
        draw_text(self.screen, f"{w.mag} / {w.reserve}", self.font_lg, C_WHITE,
                  wx + 290, wy + 8 + 4, center=False)
        # reload bar
        if w._reloading:
            rb = w.reload_progress()
            draw_bar(self.screen, wx + 12, wy + 56, 280, 10, rb, C_NEON_YELLOW)
        # Silah seçici
        for i, ww in enumerate(self.player.weapons):
            sw = 60
            sx_ = wx - (4 - i) * (sw + 6) + 240
            sy_ = wy - 56
            sel = (i == self.player.weapon_idx)
            bg = (40, 50, 80) if sel else (20, 24, 38)
            pygame.draw.rect(self.screen, bg, (sx_, sy_, sw, 46), border_radius=6)
            pygame.draw.rect(self.screen, ww.color if sel else C_HUD_DIM,
                             (sx_, sy_, sw, 46), 2, border_radius=6)
            draw_text(self.screen, str(i + 1), self.font_sm,
                      ww.color if sel else C_WHITE, sx_ + 6, sy_ + 4)
            draw_text(self.screen, ww.name[:5], self.font_xs,
                      C_WHITE, sx_ + 6, sy_ + 26)

        # Üst orta: dalga & timer
        wave_text = f"DALGA {self.waves.wave}"
        if not self.waves.in_wave and self.waves.wave > 0:
            wave_text += f"  -  Sonraki: {self.waves.inter_t:.1f}s"
        draw_text(self.screen, wave_text, self.font_md, C_NEON_PINK,
                  self.w // 2, 30, center=True)
        # Wave start animasyonu
        if self.waves.in_wave and self.waves.spawn_timer > 0 and self.elapsed < 999:
            pass  # dalga adı zaten görünüyor

        # Sol üst: skor & altın & kill
        draw_text(self.screen, f"SKOR  {self.player.score}", self.font_sm,
                  C_WHITE, 16, 12)
        draw_text(self.screen, f"ALTIN {self.player.gold}", self.font_sm,
                  (255, 210, 80), 16, 36)
        draw_text(self.screen, f"KILL  {self.player.kills}", self.font_sm,
                  C_NEON_RED, 16, 60)

        # Sağ üst: en yüksek skor
        draw_text(self.screen, f"BEST {self.high_score}", self.font_sm,
                  C_NEON_YELLOW, self.w - 16 - 130, 12)

        # Boss HP (varsa)
        boss = next((e for e in self.enemies if e.kind == Enemy.KIND_BOSS and e.alive), None)
        if boss:
            bw = 600
            bh = 24
            bx = (self.w - bw) // 2
            by = 60
            draw_bar(self.screen, bx, by, bw, bh, boss.hp / boss.max_hp,
                     C_NEON_RED, bg=(40, 10, 10))
            draw_text(self.screen, "BOSS", self.font_sm, C_WHITE,
                      bx + bw // 2, by + bh // 2, center=True)

    def _render_pause_overlay(self):
        ov = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        self.screen.blit(ov, (0, 0))
        draw_text(self.screen, "DURAKLATILDI", self.font_lg, C_NEON_CYAN,
                  self.w // 2, self.h // 2 - 130, center=True)
        for b in self.pause_buttons:
            b.draw(self.screen, self.font_sm)

    def _render_gameover_overlay(self):
        ov = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 200))
        self.screen.blit(ov, (0, 0))
        draw_text(self.screen, "OYUN BİTTİ", self.font_xl, C_NEON_RED,
                  self.w // 2, self.h // 2 - 140, center=True)
        draw_text(self.screen, f"Skor: {self.player.score}    Kill: {self.player.kills}    Dalga: {self.waves.wave}",
                  self.font_md, C_WHITE,
                  self.w // 2, self.h // 2 - 50, center=True)
        if self.player.score >= self.high_score and self.player.score > 0:
            draw_text(self.screen, "YENİ REKOR!", self.font_md, C_NEON_YELLOW,
                      self.w // 2, self.h // 2 - 10, center=True)
        for b in self.gameover_buttons:
            b.draw(self.screen, self.font_sm)

    def _render_cursor(self):
        mx, my = pygame.mouse.get_pos()
        if self.state == Game.STATE_PLAYING:
            # Crosshair
            r = 14
            col = C_NEON_CYAN
            pygame.draw.circle(self.screen, col, (mx, my), r, 2)
            pygame.draw.line(self.screen, col, (mx - r - 6, my), (mx - 4, my), 2)
            pygame.draw.line(self.screen, col, (mx + 4, my), (mx + r + 6, my), 2)
            pygame.draw.line(self.screen, col, (mx, my - r - 6), (mx, my - 4), 2)
            pygame.draw.line(self.screen, col, (mx, my + 4), (mx, my + r + 6), 2)
            pygame.draw.circle(self.screen, col, (mx, my), 2)
        else:
            # Menüde standart imleç
            pygame.draw.polygon(self.screen, C_WHITE,
                                [(mx, my), (mx + 14, my + 6),
                                 (mx + 6, my + 8), (mx + 4, my + 14)])
            pygame.draw.polygon(self.screen, C_BG_DARK,
                                [(mx, my), (mx + 14, my + 6),
                                 (mx + 6, my + 8), (mx + 4, my + 14)], 1)


# ============================================================================
# BÖLÜM 16: GİRİŞ NOKTASI
# ============================================================================

def main():
    try:
        game = Game()
        # _fire_edge başlangıç değeri
        game._fire_edge = True
        game.run()
    except Exception as e:
        # Hata durumunda terminale yaz, pygame kapat
        try:
            pygame.quit()
        except Exception:
            pass
        print("HATA:", e)
        raise


if __name__ == "__main__":
    main()
