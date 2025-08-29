import pygame

# init pygame
pygame.init()
pygame.mixer.init()

# create a window (needed for key events)
screen = pygame.display.set_mode((400, 200))
pygame.display.set_caption("Soundboard")

# load sounds
sound_a = pygame.mixer.Sound("sound_a.wav")
sound_b = pygame.mixer.Sound("sound_b.wav")

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_a:
                sound_a.play()
            elif event.key == pygame.K_b:
                sound_b.play()
            elif event.key == pygame.K_ESCAPE:
                running = False
