import json
from pathlib import Path

import sc2
from sc2.constants import *
from sc2 import Race, Difficulty
from sc2.player import Bot, Computer

class MyBot(sc2.BotAI):

  def __init__(self):
    super()
    self.scv_counter = 0
    self.extractor_started = False
    self.moved_workers_to_gas = False
    self.moved_workers_from_gas = False
    self.scout_index = -1
    self.scout_tag = None
    # self.tech_lab_build = False

  with open(Path(__file__).parent / "../botinfo.json") as f:
    NAME = json.load(f)["name"]

  async def on_step(self, iteration):
    if iteration == 0:
      await self.chat_send(f"Name: {self.NAME}")

    cc = self.units(COMMANDCENTER)
    if not cc.exists:
      target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position
      for unit in self.workers | self.units(MARINE):
        await self.do(unit.attack(target))
      return
    else:
      cc = cc.first

    # moar SCVs
    for scv in self.units(SCV).idle:
      await self.do(scv.gather(self.state.mineral_field.closest_to(cc)))

    if self.can_afford(SCV) and self.workers.amount < 16 and cc.noqueue:
      await self.do(cc.train(SCV))

    # Do we have enoguh supply depots
    elif self.supply_left < (2 if self.units(BARRACKS).amount < 3 else 4):
      if self.can_afford(SUPPLYDEPOT):
        await self.build(SUPPLYDEPOT, near=cc.position.towards(self.game_info.map_center, 3))

    # Gas
    if not self.extractor_started:
      if self.can_afford(REFINERY):
        SCVs = self.workers.random
        target = self.state.vespene_geyser.closest_to(SCVs.position)
        err = await self.do(SCVs.build(REFINERY, target))
        if not err:
          self.extractor_started = True

    if self.units(REFINERY).ready.exists and not self.moved_workers_to_gas:
      self.moved_workers_to_gas = True
      refinery = self.units(REFINERY).first
      for SCVs in self.workers.random_group_of(3):
        await self.do(SCVs.gather(refinery))

    if self.known_enemy_units.amount > 0 and iteration % 5 == 0:
      for unit in self.marines_excluding_scout():
        await self.do(unit.attack(self.known_enemy_units[0]))
    elif self.units(MARINE).amount > 14 and iteration % 5 == 0:
      for unit in self.marines_excluding_scout():
        await self.do(unit.attack(self.enemy_start_locations[0]))

    # Barracks
    elif self.units(BARRACKS).amount < 3 or (self.minerals > 400 and self.units(BARRACKS).amount < 4):
      # if self.can_afford(BARRACKSTECHLAB) and not self.tech_lab_build:
      #   for barrack in self.units(BARRACKS).ready.noqueue:
      #     print("can_afford(BARRACKSTECHLAB)")
      #     if barrack.add_on_tag == 0:
      #       await self.do(barrack.build(BARRACKSTECHLAB))
      if self.can_afford(BARRACKS):
        await self.build(BARRACKS, near=cc.position.towards(self.game_info.map_center, 7))

    # Marine
    for rax in self.units(BARRACKS).ready.noqueue:
      if not self.can_afford(MARINE):
        break
      await self.do(rax.train(MARINE))

    for depot in self.units(SUPPLYDEPOT).ready:
      if not self.can_afford(MORPH_SUPPLYDEPOT_LOWER):
        break
      await self.do(depot(MORPH_SUPPLYDEPOT_LOWER))

    # Run scouting subsystem
    await self.scout(iteration)

  def marines_excluding_scout(self):
    return (x for x in self.units(MARINE) if x.tag != self.scout_tag)

  def find_marine_by_tag(self, unit_tag):
    for marine in self.units(MARINE):
      if marine.tag == unit_tag:
        return marine
    return None

  async def scout(self, iteration):

    if not iteration % 150 == 0:
      return

    scout = self.find_marine_by_tag(self.scout_tag)

    print(f'Found scout {scout}')

    if scout == None:
      # Assign scout if available
      if self.units(MARINE).idle.amount > 3:
        marine = self.units(MARINE).first
        print(f'Assigned marine {marine.tag} to scout')
        self.scout_tag = marine.tag
        scout = marine

    # Scout
    if scout:
      print(f'Scouting with {scout}')
      enemy_positions = [x.position for x in self.enemy_start_locations]
      expansion_positions = [x.position for x in self.expansion_locations]
      scout_set = enemy_positions + expansion_positions
      self.scout_index = (self.scout_index + 1) % len(scout_set)

      print(f'Next scout target index: {self.scout_index} from {len(scout_set)}')

      await self.do(scout.attack(scout_set[self.scout_index]))
