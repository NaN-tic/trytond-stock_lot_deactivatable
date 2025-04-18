from trytond.pool import Pool, PoolMeta


class ShipmentOutReturn(metaclass=PoolMeta):
    __name__ = 'stock.shipment.out.return'

    @classmethod
    def receive(cls, shipments):
        pool = Pool()
        Lot = pool.get('stock.lot')
        super().receive(shipments)

        to_save = []
        for shipment in shipments:
            for move in shipment.incoming_moves:
                if move.quantity <= 0:
                    continue
                lot = move.lot
                if lot and lot.active == False:
                    lot.active = True
                    to_save.append(lot)
        Lot.save(to_save)
