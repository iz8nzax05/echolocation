#!/usr/bin/env python3
"""
Echolocation Game
Navigate using visual sound waves. You're blind except when you ping and see the sound waves bounce back.
"""

import math
import random
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional

import pygame
import numpy as np

# --- Screen settings ---
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (0, 0, 0)  # Pure black
PLAYER_COLOR = (255, 255, 255)  # White dot
PLAYER_RADIUS = 4

# --- Wave settings ---
WAVE_SPEED = 300  # pixels per second
SOUND_SPEED = WAVE_SPEED  # Same as wave speed for timing
MAX_DISTANCE = 2000  # Maximum raycast distance
RAY_ANGLE_STEP = 1.5  # Degrees between rays (360/240 = 1.5 degrees for 240 rays)

# --- Visual settings ---
MIN_BRIGHTNESS = 10
MAX_BRIGHTNESS = 255
FADE_DURATION = 2.0  # Seconds for revealed areas to fade back to black
NOISE_INTENSITY = 0.15  # 0-1, how much noise overlay

# --- Player movement ---
PLAYER_SPEED = 200  # pixels per second

# --- Colors ---
WAVE_COLOR = (0, 255, 200)  # Cyan for outgoing waves
REVEAL_COLOR = (100, 200, 150)  # Greenish for revealed surfaces


@dataclass
class EchoWave:
    """Outgoing sound wave from player"""
    origin_x: float
    origin_y: float
    angle: float  # In radians
    creation_time: float
    max_distance: float = MAX_DISTANCE


@dataclass
class ReturnWave:
    """Returning wave that reveals surfaces"""
    hit_point: Tuple[float, float]
    player_pos: Tuple[float, float]
    creation_time: float
    distance: float
    angle: float  # Angle from player to hit point
    wall: Optional['Wall'] = None  # Which wall was hit


@dataclass
class RevealedWallSegment:
    """A segment of a wall that has been revealed"""
    x1: float
    y1: float
    x2: float
    y2: float
    brightness: float  # 0-255
    reveal_time: float
    distance: float
    wall: Optional['Wall'] = None  # Which wall this segment belongs to
    hit_x: float = 0.0  # Where the ray actually hit
    hit_y: float = 0.0  # Where the ray actually hit


class Wall:
    """A wall/obstacle in the environment"""
    def __init__(self, x1: float, y1: float, x2: float, y2: float):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
    
    def distance_to_point(self, px: float, py: float) -> float:
        """Calculate minimum distance from a point to this wall segment"""
        # Vector from wall start to end
        wall_dx = self.x2 - self.x1
        wall_dy = self.y2 - self.y1
        wall_length_sq = wall_dx * wall_dx + wall_dy * wall_dy
        
        if wall_length_sq < 1e-10:
            # Wall is a point, return distance to that point
            return math.sqrt((px - self.x1)**2 + (py - self.y1)**2)
        
        # Vector from wall start to point
        to_point_dx = px - self.x1
        to_point_dy = py - self.y1
        
        # Project point onto wall line
        t = max(0, min(1, (to_point_dx * wall_dx + to_point_dy * wall_dy) / wall_length_sq))
        
        # Closest point on wall segment
        closest_x = self.x1 + t * wall_dx
        closest_y = self.y1 + t * wall_dy
        
        # Distance from point to closest point on wall
        return math.sqrt((px - closest_x)**2 + (py - closest_y)**2)
    
    def intersect_ray(self, origin_x: float, origin_y: float, angle: float) -> Optional[Tuple[float, float, float]]:
        """
        Check if ray intersects this wall.
        Returns (hit_x, hit_y, distance) or None if no intersection.
        """
        # Ray direction
        dx = math.cos(angle)
        dy = math.sin(angle)
        
        # Wall vector
        wall_dx = self.x2 - self.x1
        wall_dy = self.y2 - self.y1
        
        # Check if ray and wall are parallel
        denom = wall_dx * dy - wall_dy * dx
        if abs(denom) < 1e-10:
            return None
        
        # Calculate intersection
        t = ((self.x1 - origin_x) * dy - (self.y1 - origin_y) * dx) / denom
        s = ((self.x1 - origin_x) * wall_dy - (self.y1 - origin_y) * wall_dx) / denom
        
        # Check if intersection is within wall segment and ray direction
        if 0 <= t <= 1 and s >= 0:
            hit_x = self.x1 + t * wall_dx
            hit_y = self.y1 + t * wall_dy
            distance = math.sqrt((hit_x - origin_x)**2 + (hit_y - origin_y)**2)
            return (hit_x, hit_y, distance)
        
        return None


class EcholocationGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Echolocation Game")
        self.clock = pygame.time.Clock()
        self.running = True
        
        # Player position
        self.player_x = SCREEN_WIDTH // 2
        self.player_y = SCREEN_HEIGHT // 2
        
        # Game state
        self.current_time = 0.0
        self.echo_waves: List[EchoWave] = []
        self.return_waves: List[ReturnWave] = []
        self.revealed_segments: List[RevealedWallSegment] = []
        self.auto_ping_enabled = False  # Toggle for continuous pinging
        self.last_auto_ping_time = 0.0  # Time of last auto-ping
        self.auto_ping_interval = 0.05  # Ping every 0.05 seconds (20 times per second max)
        
        # Create environment with walls
        self.walls = self.create_environment()
        
        # Noise texture for sonar effect
        self.noise_surface = self.create_noise_texture()
        
        # Surface for revealed areas (we'll draw on this)
        self.reveal_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.reveal_surface.set_colorkey((0, 0, 0))  # Black is transparent
        
    def create_environment(self) -> List[Wall]:
        """Create a test environment with walls"""
        walls = []
        
        # Border walls
        margin = 50
        walls.append(Wall(margin, margin, SCREEN_WIDTH - margin, margin))  # Top
        walls.append(Wall(SCREEN_WIDTH - margin, margin, SCREEN_WIDTH - margin, SCREEN_HEIGHT - margin))  # Right
        walls.append(Wall(SCREEN_WIDTH - margin, SCREEN_HEIGHT - margin, margin, SCREEN_HEIGHT - margin))  # Bottom
        walls.append(Wall(margin, SCREEN_HEIGHT - margin, margin, margin))  # Left
        
        # Spawn area (center) - keep clear
        spawn_x = SCREEN_WIDTH // 2
        spawn_y = SCREEN_HEIGHT // 2
        spawn_clear_radius = 150  # Clear area around spawn
        
        # Some interior obstacles
        # Box in top-left (away from spawn)
        box_size = 150
        box_x = 200
        box_y = 200
        # Check if box would overlap spawn area
        box_center_x = box_x + box_size / 2
        box_center_y = box_y + box_size / 2
        dist_to_spawn = math.sqrt((box_center_x - spawn_x)**2 + (box_center_y - spawn_y)**2)
        if dist_to_spawn < spawn_clear_radius + box_size:
            # Move box further away
            box_x = 100
            box_y = 100
        
        walls.append(Wall(box_x, box_y, box_x + box_size, box_y))
        walls.append(Wall(box_x + box_size, box_y, box_x + box_size, box_y + box_size))
        walls.append(Wall(box_x + box_size, box_y + box_size, box_x, box_y + box_size))
        walls.append(Wall(box_x, box_y + box_size, box_x, box_y))
        
        # Box in bottom-right (away from spawn)
        box_x2 = SCREEN_WIDTH - 350
        box_y2 = SCREEN_HEIGHT - 350
        # Check if box would overlap spawn area
        box2_center_x = box_x2 + box_size / 2
        box2_center_y = box_y2 + box_size / 2
        dist_to_spawn2 = math.sqrt((box2_center_x - spawn_x)**2 + (box2_center_y - spawn_y)**2)
        if dist_to_spawn2 < spawn_clear_radius + box_size:
            # Move box further away
            box_x2 = SCREEN_WIDTH - 250
            box_y2 = SCREEN_HEIGHT - 250
        
        walls.append(Wall(box_x2, box_y2, box_x2 + box_size, box_y2))
        walls.append(Wall(box_x2 + box_size, box_y2, box_x2 + box_size, box_y2 + box_size))
        walls.append(Wall(box_x2 + box_size, box_y2 + box_size, box_x2, box_y2 + box_size))
        walls.append(Wall(box_x2, box_y2 + box_size, box_x2, box_y2))
        
        # Vertical wall in middle (with gap around spawn)
        mid_x = SCREEN_WIDTH // 2
        gap_size = spawn_clear_radius + 50
        walls.append(Wall(mid_x, 300, mid_x, spawn_y - gap_size))  # Top part
        walls.append(Wall(mid_x, spawn_y + gap_size, mid_x, SCREEN_HEIGHT - 300))  # Bottom part
        
        # Horizontal wall (with gap around spawn)
        mid_y = SCREEN_HEIGHT // 2
        walls.append(Wall(400, mid_y, spawn_x - gap_size, mid_y))  # Left part
        walls.append(Wall(spawn_x + gap_size, mid_y, SCREEN_WIDTH - 400, mid_y))  # Right part
        
        # Hollow square room (house) - positioned away from spawn
        room_size = 200
        room_x = 800  # Position on the right side
        room_y = 200  # Position near top
        door_width = 60  # Opening width for doorway
        
        # Top wall
        walls.append(Wall(room_x, room_y, room_x + room_size, room_y))
        # Right wall
        walls.append(Wall(room_x + room_size, room_y, room_x + room_size, room_y + room_size))
        # Bottom wall (with doorway opening)
        walls.append(Wall(room_x, room_y + room_size, room_x + (room_size - door_width) / 2, room_y + room_size))  # Left part
        walls.append(Wall(room_x + (room_size + door_width) / 2, room_y + room_size, room_x + room_size, room_y + room_size))  # Right part
        # Left wall
        walls.append(Wall(room_x, room_y, room_x, room_y + room_size))
        
        return walls
    
    def create_noise_texture(self) -> pygame.Surface:
        """Create a noise texture for sonar aesthetic"""
        noise = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        # pygame.surfarray expects (width, height, channels) format
        noise_array = np.random.randint(0, 50, (SCREEN_WIDTH, SCREEN_HEIGHT, 3), dtype=np.uint8)
        pygame.surfarray.blit_array(noise, noise_array)
        noise.set_alpha(int(255 * NOISE_INTENSITY))
        return noise
    
    def cast_ray(self, origin_x: float, origin_y: float, angle: float) -> Optional[Tuple[float, float, float, 'Wall']]:
        """
        Cast a ray and find the closest wall intersection.
        Returns (hit_x, hit_y, distance, wall) or None.
        """
        closest_hit = None
        closest_wall = None
        min_distance = MAX_DISTANCE
        
        for wall in self.walls:
            hit = wall.intersect_ray(origin_x, origin_y, angle)
            if hit:
                hit_x, hit_y, distance = hit
                if distance < min_distance:
                    min_distance = distance
                    closest_hit = (hit_x, hit_y, distance)
                    closest_wall = wall
        
        if closest_hit:
            return (*closest_hit, closest_wall)
        return None
    
    def ping(self):
        """Send out a ping - cast rays in all directions"""
        num_rays = int(360 / RAY_ANGLE_STEP)
        
        for i in range(num_rays):
            angle_deg = i * RAY_ANGLE_STEP
            angle_rad = math.radians(angle_deg)
            
            # Cast ray
            hit = self.cast_ray(self.player_x, self.player_y, angle_rad)
            
            if hit:
                hit_x, hit_y, distance, wall = hit
                
                # Create return wave that will arrive after travel time
                travel_time = distance / SOUND_SPEED
                
                return_wave = ReturnWave(
                    hit_point=(hit_x, hit_y),
                    player_pos=(self.player_x, self.player_y),
                    creation_time=self.current_time,
                    distance=distance,
                    angle=angle_rad,
                    wall=wall
                )
                
                # Schedule the reveal for when the wave returns
                # We'll check this in update()
                self.return_waves.append(return_wave)
        
        # Also create visual echo wave (expanding ring)
        echo_wave = EchoWave(
            origin_x=self.player_x,
            origin_y=self.player_y,
            angle=0,  # Not used for visual wave
            creation_time=self.current_time
        )
        self.echo_waves.append(echo_wave)
    
    def update(self, dt: float):
        """Update game state"""
        self.current_time += dt
        
        # Update player movement
        keys = pygame.key.get_pressed()
        dx, dy = 0, 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy -= PLAYER_SPEED * dt
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy += PLAYER_SPEED * dt
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx -= PLAYER_SPEED * dt
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx += PLAYER_SPEED * dt
        
        # Try to move, but check collisions first
        new_x = self.player_x + dx
        new_y = self.player_y + dy
        
        # Check collision with player radius
        player_radius = PLAYER_RADIUS + 2  # Slightly larger for collision detection
        
        # Try X movement first
        if not self.check_collision(new_x, self.player_y, player_radius):
            self.player_x = new_x
        # Try Y movement
        if not self.check_collision(self.player_x, new_y, player_radius):
            self.player_y = new_y
        
        # Keep player in bounds
        margin = 20
        self.player_x = max(margin, min(SCREEN_WIDTH - margin, self.player_x))
        self.player_y = max(margin, min(SCREEN_HEIGHT - margin, self.player_y))
        
        # Process return waves - check if they've reached the player
        waves_to_remove = []
        for return_wave in self.return_waves:
            travel_time = return_wave.distance / SOUND_SPEED
            elapsed = self.current_time - return_wave.creation_time
            
            if elapsed >= travel_time:
                # Wave has returned - reveal the wall segment
                hit_x, hit_y = return_wave.hit_point
                
                # Calculate brightness based on distance
                brightness = MAX_BRIGHTNESS - (return_wave.distance / MAX_DISTANCE) * (MAX_BRIGHTNESS - MIN_BRIGHTNESS)
                brightness = max(MIN_BRIGHTNESS, min(MAX_BRIGHTNESS, brightness))
                
                # Create a small segment of the wall around the hit point
                if return_wave.wall:
                    # Get the wall endpoints
                    wall = return_wave.wall
                    # Create a segment around the hit point (about 10 pixels on each side)
                    segment_length = 20
                    wall_dx = wall.x2 - wall.x1
                    wall_dy = wall.y2 - wall.y1
                    wall_length = math.sqrt(wall_dx**2 + wall_dy**2)
                    
                    if wall_length > 0:
                        # Normalize direction
                        norm_dx = wall_dx / wall_length
                        norm_dy = wall_dy / wall_length
                        
                        # Calculate segment endpoints
                        seg_x1 = hit_x - norm_dx * segment_length
                        seg_y1 = hit_y - norm_dy * segment_length
                        seg_x2 = hit_x + norm_dx * segment_length
                        seg_y2 = hit_y + norm_dy * segment_length
                        
                        # Clamp to wall bounds
                        if wall.x1 < wall.x2:
                            seg_x1 = max(wall.x1, min(wall.x2, seg_x1))
                            seg_x2 = max(wall.x1, min(wall.x2, seg_x2))
                        else:
                            seg_x1 = max(wall.x2, min(wall.x1, seg_x1))
                            seg_x2 = max(wall.x2, min(wall.x1, seg_x2))
                        
                        if wall.y1 < wall.y2:
                            seg_y1 = max(wall.y1, min(wall.y2, seg_y1))
                            seg_y2 = max(wall.y1, min(wall.y2, seg_y2))
                        else:
                            seg_y1 = max(wall.y2, min(wall.y1, seg_y1))
                            seg_y2 = max(wall.y2, min(wall.y1, seg_y2))
                        
                        revealed_segment = RevealedWallSegment(
                            x1=seg_x1,
                            y1=seg_y1,
                            x2=seg_x2,
                            y2=seg_y2,
                            brightness=brightness,
                            reveal_time=self.current_time,
                            distance=return_wave.distance,
                            wall=wall,
                            hit_x=hit_x,
                            hit_y=hit_y
                        )
                        self.revealed_segments.append(revealed_segment)
                
                waves_to_remove.append(return_wave)
        
        # Remove processed waves
        for wave in waves_to_remove:
            self.return_waves.remove(wave)
        
        # Fade revealed segments
        segments_to_remove = []
        for segment in self.revealed_segments:
            elapsed = self.current_time - segment.reveal_time
            if elapsed > FADE_DURATION:
                segments_to_remove.append(segment)
            else:
                # Fade brightness
                fade_progress = elapsed / FADE_DURATION
                segment.brightness = segment.brightness * (1 - fade_progress)
        
        for segment in segments_to_remove:
            self.revealed_segments.remove(segment)
        
        # Limit total revealed segments to prevent memory issues (keep oldest)
        MAX_REVEALED_SEGMENTS = 5000
        if len(self.revealed_segments) > MAX_REVEALED_SEGMENTS:
            # Sort by reveal time and remove oldest
            self.revealed_segments.sort(key=lambda s: s.reveal_time)
            self.revealed_segments = self.revealed_segments[-MAX_REVEALED_SEGMENTS:]
        
        # Remove old echo waves (visual only, they expand and fade)
        self.echo_waves = [w for w in self.echo_waves if self.current_time - w.creation_time < 2.0]
        
        # Auto-ping if enabled (with throttling to prevent crashes)
        if self.auto_ping_enabled:
            if self.current_time - self.last_auto_ping_time >= self.auto_ping_interval:
                self.ping()
                self.last_auto_ping_time = self.current_time
    
    def check_collision(self, x: float, y: float, radius: float) -> bool:
        """Check if a circle at (x, y) with given radius collides with any wall"""
        for wall in self.walls:
            distance = wall.distance_to_point(x, y)
            if distance < radius:
                return True
        return False
    
    def clip_line_at_walls(self, x1: float, y1: float, x2: float, y2: float, ignore_wall: Optional[Wall] = None) -> Tuple[float, float]:
        """
        Clip a line at the first wall it hits.
        Returns the clipped endpoint (closest point on line that doesn't pass through walls).
        """
        # Line direction
        line_dx = x2 - x1
        line_dy = y2 - y1
        
        closest_intersection = None
        min_t = 1.0  # Parameter along line (0 = start, 1 = end)
        
        # Check intersection with all walls
        for wall in self.walls:
            if wall == ignore_wall:
                continue
            
            # Wall direction
            wall_dx = wall.x2 - wall.x1
            wall_dy = wall.y2 - wall.y1
            
            # Check if line and wall are parallel
            denom = line_dx * wall_dy - line_dy * wall_dx
            if abs(denom) < 1e-10:
                continue
            
            # Calculate intersection parameters
            # Line: (x1, y1) + t * (line_dx, line_dy)
            # Wall: (wall.x1, wall.y1) + s * (wall_dx, wall_dy)
            dx = wall.x1 - x1
            dy = wall.y1 - y1
            
            t = (dx * wall_dy - dy * wall_dx) / denom
            s = (dx * line_dy - dy * line_dx) / denom
            
            # Check if intersection is within both line segment and wall segment
            if 0 <= t <= 1 and 0 <= s <= 1:
                if t < min_t:
                    min_t = t
                    closest_intersection = (x1 + t * line_dx, y1 + t * line_dy)
        
        if closest_intersection:
            return closest_intersection
        return (x2, y2)
    
    def draw(self):
        """Draw everything"""
        # Clear screen to black
        self.screen.fill(BACKGROUND_COLOR)
        
        # Clear reveal surface
        self.reveal_surface.fill((0, 0, 0))
        
        # Draw lines from player to revealed segments (sonar lines) and dots
        for segment in self.revealed_segments:
            if segment.brightness > MIN_BRIGHTNESS:
                hit_x, hit_y = segment.hit_x, segment.hit_y
                
                # Check if line from current player position to hit point would be blocked
                # Clip the line and see if it reaches the hit point
                clipped_x, clipped_y = self.clip_line_at_walls(
                    self.player_x, self.player_y, hit_x, hit_y, segment.wall
                )
                
                # Check if the clipped line actually reaches the hit point
                dist_to_hit = math.sqrt((clipped_x - hit_x)**2 + (clipped_y - hit_y)**2)
                line_reaches_hit = dist_to_hit < 5  # Small tolerance for floating point errors
                
                # Only draw if line can reach the hit point (not blocked by another wall)
                if line_reaches_hit:
                    # Draw green dot at the hit point (where line hits wall)
                    green_brightness = int(segment.brightness * 0.8)
                    dot_color = (0, green_brightness, green_brightness // 2)
                    pygame.draw.circle(
                        self.reveal_surface,
                        dot_color,
                        (int(hit_x), int(hit_y)),
                        3  # Dot radius
                    )
                    
                    # Draw the sonar line (visual only, clipped at walls)
                    alpha = int(segment.brightness * 0.2)
                    color = (0, alpha, alpha // 2)
                    pygame.draw.line(
                        self.reveal_surface,
                        color,
                        (int(self.player_x), int(self.player_y)),
                        (int(clipped_x), int(clipped_y)),
                        1
                    )
        
        # Blit reveal surface onto main screen
        self.screen.blit(self.reveal_surface, (0, 0))
        
        # Draw player
        pygame.draw.circle(self.screen, PLAYER_COLOR, (int(self.player_x), int(self.player_y)), PLAYER_RADIUS)
        
        # Apply noise overlay
        self.screen.blit(self.noise_surface, (0, 0))
        
        pygame.display.flip()
    
    def handle_events(self):
        """Handle input events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    self.ping()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_t:
                    # Toggle auto-ping
                    self.auto_ping_enabled = not self.auto_ping_enabled
    
    def run(self):
        """Main game loop"""
        while self.running:
            dt = self.clock.tick(60) / 1000.0  # Delta time in seconds
            
            self.handle_events()
            self.update(dt)
            self.draw()
        
        pygame.quit()


def main():
    game = EcholocationGame()
    game.run()


if __name__ == "__main__":
    main()

