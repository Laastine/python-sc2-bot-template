import json
from pathlib import Path

import sc2
from sc2.constants import *
from sc2 import Race, Difficulty
from sc2.player import Bot, Computer

class MyBot(sc2.BotAI):

  def __init__(self):
    super()
    self.scout_index = -1
    self.scout_tag = None
    self.tech_lab_counter = 0
    self.weapons_started = False
    self.armor_started = False
    self.barrack_iterator = -1

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

    await self.scvs(iteration, cc)

    await self.refinery()

    await self.attack(iteration, cc)

    await self.build_units(iteration)

    await self.upgrade(iteration, cc)

    # Run scouting subsystem
    await self.scout(iteration)

    await self.engi_bay(cc)

    await self.medivacs(cc)

    await self.expand()

  def attack_units_excluding_scout(self):
    def is_not_scout(unit):
      return unit.tag != self.scout_tag
    return self.units(MARINE).filter(is_not_scout) | self.units(MARAUDER) | self.units(MEDIVAC)

  def find_marine_by_tag(self, unit_tag):
    for marine in self.units(MARINE):
      if marine.tag == unit_tag:
        return marine
    return None

  async def upgrade(self, iteration, cc):
    # Barracks
    if self.units(BARRACKS).amount < self.units(COMMANDCENTER).ready.amount * 3 and self.can_afford(BARRACKS):
        await self.build(BARRACKS, near=cc.position.towards(self.game_info.map_center, 7))

    if self.units(BARRACKSTECHLAB).amount < 1 and self.units(BARRACKS).amount > 1 and not self.already_pending(BARRACKSTECHLAB):
      for barrack in self.units(BARRACKS).ready:
        if barrack.add_on_tag == 0 and not barrack.has_add_on:
          await self.do(barrack.build(BARRACKSTECHLAB))

    if self.units(BARRACKSTECHLAB).amount > 0:
      for lab in self.units(BARRACKSTECHLAB).ready:
        await self.do(lab.build(RESEARCH_CONCUSSIVESHELLS))
        await self.do(lab.build(RESEARCH_COMBATSHIELD))

  async def build_units(self, iteration):
    if iteration % 100 == 0:
      return

    build_rotation = [MARAUDER, MARINE]
    self.barrack_iterator += 1
    unit = build_rotation[self.barrack_iterator % len(build_rotation)]

    # Marine
    for rax in self.units(BARRACKS).ready.noqueue:
      if not self.can_afford(MARINE) or (self.can_afford(BARRACKSTECHLAB) and self.units(BARRACKSTECHLAB).amount > 0):
        break
      if unit == MARAUDER:
        if self.units(BARRACKSTECHLAB).amount and self.can_afford(MARAUDER):
          await self.do(rax.train(MARAUDER))
        else:
          await self.do(rax.train(MARINE))
      elif unit == MARINE:
        await self.do(rax.train(MARINE))

    for depot in self.units(SUPPLYDEPOT).ready:
      if not self.can_afford(MORPH_SUPPLYDEPOT_LOWER):
        break
      await self.do(depot(MORPH_SUPPLYDEPOT_LOWER))

  async def attack(self, iteration, cc):
    staging_pick_distance = 5
    reaction_distance = 15
    all_units = self.units(MARINE) | self.units(MARAUDER) | self.units(MEDIVAC)

    rally_point = cc.position.towards(self.game_info.map_center, distance=15)

    near_cc_count = self.attack_units_excluding_scout().closer_than(staging_pick_distance, cc.position).amount
    near_rally_count = self.attack_units_excluding_scout().closer_than(staging_pick_distance, rally_point).amount

    base_attackers = self.known_enemy_units.closer_than(10, cc)
    if base_attackers.amount > 3:
      for unit in self.attack_units_excluding_scout() | self.units(SCV):
        await self.do(unit.attack(base_attackers[0].position))

    elif self.known_enemy_units.amount > 0 and (near_cc_count + near_rally_count > 15) and iteration % 5 == 0:
      closest_enemy = self.known_enemy_units.closest_to(cc)
      for unit in self.attack_units_excluding_scout().closer_than(reaction_distance, closest_enemy):
        await self.do(unit.attack(closest_enemy))

    elif near_cc_count > 15 and iteration % 100 == 0:
      for unit in self.attack_units_excluding_scout().closer_than(staging_pick_distance, cc.position):
        await self.do(unit.move(rally_point))

    elif near_rally_count > 40 and iteration > 6000:
      for unit in self.attack_units_excluding_scout().closer_than(staging_pick_distance, rally_point):
        await self.do(unit.attack(self.enemy_start_locations[0]))


  async def scvs(self, iteration, cc):
    # make scvs
    for cc in self.units(COMMANDCENTER).ready.noqueue:
      if self.can_afford(SCV) and self.units(SCV).amount < self.units(COMMANDCENTER).amount * 19:
        await self.do(cc.train(SCV))

    # gather closest mineral
    for scv in self.units(SCV).idle:
      await self.do(scv.gather(self.state.mineral_field.closest_to(scv)))

    # distribute
    await self.distribute_workers()

    # Do we have enough supply depots
    if self.supply_left < (4 if self.units(BARRACKS).amount < 3 else 6):
      if self.can_afford(SUPPLYDEPOT) and not self.already_pending(SUPPLYDEPOT):
        await self.build(SUPPLYDEPOT, near=cc.position.towards(self.game_info.map_center, 3))

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

  async def expand(self):
    if self.units(COMMANDCENTER).amount < 2 and self.minerals > 400:
      await self.expand_now()

  async def engi_bay(self, cc):
    if self.units(MARINE).amount > 6 and self.units(REFINERY).amount > 0 and self.units(ENGINEERINGBAY).amount < 1 and not self.already_pending(ENGINEERINGBAY) and self.can_afford(ENGINEERINGBAY):
      await self.build(ENGINEERINGBAY, near=cc.position.towards(self.game_info.map_center, 3))
    for bay in self.units(ENGINEERINGBAY).ready.noqueue:
      if not self.weapons_started and self.can_afford(ENGINEERINGBAYRESEARCH_TERRANINFANTRYWEAPONSLEVEL1):
        self.weapons_started = True
        await self.do(bay(ENGINEERINGBAYRESEARCH_TERRANINFANTRYWEAPONSLEVEL1))
    for bay in self.units(ENGINEERINGBAY).ready.noqueue:
      if not self.armor_started and self.can_afford(ENGINEERINGBAYRESEARCH_TERRANINFANTRYARMORLEVEL1):
        self.armor_started = True
        await self.do(bay(ENGINEERINGBAYRESEARCH_TERRANINFANTRYARMORLEVEL1))

  async def refinery(self):
    if self.can_afford(REFINERY) and not self.already_pending(REFINERY) and self.units(REFINERY).amount < 1:
      SCVs = self.workers.random
      target = self.state.vespene_geyser.closest_to(SCVs.position)
      await self.do(SCVs.build(REFINERY, target))

  async def medivacs(self, cc):
    if self.units(ENGINEERINGBAY).amount > 0 and self.can_afford(FACTORY) and self.units(FACTORY).amount < 1 and not self.already_pending(FACTORY):
      await self.build(FACTORY, near=cc.position.towards(self.game_info.map_center, 8))
    if self.units(FACTORY).ready.amount > 0 and self.can_afford(STARPORT) and self.units(STARPORT).amount < 1 and not self.already_pending(STARPORT):
      await self.build(STARPORT, near=cc.position.towards(self.game_info.map_center, 4))
    for starport in self.units(STARPORT).ready.noqueue:
      if not self.can_afford(MEDIVAC):
        break
      await self.do(starport.train(MEDIVAC))
