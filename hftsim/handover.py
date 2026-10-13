class GroundAccess:
    """Discrete antenna acquisition, tracking and MBB.

    Acquisitions must remain visible at every sampled epoch. Routing may use either
    ready terminal. Active terminal retained; spare may be retargeted with hysteresis.
    No terminal or overlap guarantee is implied by having two antennas.
    """
    def __init__(self, antennas=2, acquire_s=20, hysteresis_deg=5):
        self.antennas, self.acquire_s = antennas, acquire_s
        self.hysteresis_deg = hysteresis_deg
        self.slots = {}  # satellite -> ready time
        self.active = None
        self.events = []

    def update(self, t, visible_scores):
        for satellite in list(self.slots):
            if satellite not in visible_scores:
                del self.slots[satellite]
                self.events.append(dict(time_s=t, kind='lost_visibility', satellite=satellite))
        for satellite in sorted(visible_scores, key=lambda s: (-visible_scores[s], s)):
            if len(self.slots) >= self.antennas:
                break
            if satellite not in self.slots:
                self.slots[satellite] = t+self.acquire_s
                self.events.append(dict(time_s=t, kind='acquire_started', satellite=satellite))
        # Retarget only a ready spare, so an in-progress acquisition is not starved.
        spare = [s for s, ready in self.slots.items() if s != self.active and ready <= t]
        outside = [s for s in visible_scores if s not in self.slots]
        if self.antennas == 2 and self.active in self.slots and spare and outside:
            worst = min(spare, key=lambda s: visible_scores[s])
            best = max(outside, key=lambda s: visible_scores[s])
            if visible_scores[best] > visible_scores[worst]+self.hysteresis_deg:
                del self.slots[worst]
                self.slots[best] = t+self.acquire_s
                self.events.append(dict(time_s=t, kind='spare_retarget', satellite=best))
        return sorted(s for s, ready in self.slots.items() if ready <= t)

    def choose(self, t, satellite):
        if satellite != self.active:
            if self.active is not None and satellite is not None:
                overlap = self.active in self.slots and self.slots[self.active] <= t
                self.events.append(dict(time_s=t, kind='handover', satellite=satellite,
                                        previous=self.active, make_before_break=overlap))
            elif satellite is not None:
                self.events.append(dict(time_s=t, kind='service_acquired', satellite=satellite))
            self.active = satellite
