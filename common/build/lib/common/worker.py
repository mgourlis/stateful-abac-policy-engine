import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from common.core.database import AsyncSessionLocal
from common.models import Realm
from common.services.sync_service import SyncService


logger = logging.getLogger(__name__)

class SchedulerWorker:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.known_jobs = set()

    async def run_sync_task(self, realm_id: int):
        """
        The actual task logic using standard SyncService.
        """
        logger.info(f"Executing scheduled sync for Realm ID: {realm_id}")
        async with AsyncSessionLocal() as session:
            try:
                service = SyncService(session)
                await service.sync_realm(realm_id)
            except Exception as e:
                logger.error(f"Error during sync for Realm {realm_id}: {e}")

    async def refresh_jobs(self):
        """
        Polls the database for changes in RealmKeycloakConfig and updates the scheduler.
        """
        logger.debug("Refreshing scheduler jobs from database...")
        async with AsyncSessionLocal() as db:
            # Fetch all realms with keycloak config
            stmt = select(Realm).options(selectinload(Realm.keycloak_config))
            result = await db.execute(stmt)
            realms = result.scalars().all()

            current_active_realm_ids = set()

            for realm in realms:
                if not realm.keycloak_config or not realm.keycloak_config.sync_cron:
                    continue
                
                # Check for enabled sync_cron string
                cron_str = realm.keycloak_config.sync_cron
                if not cron_str.strip():
                    continue

                job_id = f"sync_realm_{realm.id}"
                current_active_realm_ids.add(job_id)

                # optimization: don't re-add if exists (APScheduler replace_existing handles updates, 
                # but we can skip if nothing changed - though checking change is complex, 
                # just replacing is safer and acceptable for low volume)
                
                try:
                    trigger = CronTrigger.from_crontab(cron_str)
                    
                    # We check if job exists to avoid constant "Added job" logs if using logging in add_job
                    # But replace_existing=True ensures updates are applied
                    self.scheduler.add_job(
                        self.run_sync_task,
                        trigger=trigger,
                        id=job_id,
                        replace_existing=True,
                        args=[realm.id]
                    )
                    if job_id not in self.known_jobs:
                        logger.info(f"Scheduled sync for Realm {realm.name} ({cron_str})")
                        self.known_jobs.add(job_id)
                        
                except Exception as e:
                    logger.error(f"Invalid cron '{cron_str}' for Realm {realm.name}: {e}")

            # Remove obsolete jobs
            jobs_to_remove = self.known_jobs - current_active_realm_ids
            for job_id in jobs_to_remove:
                self.scheduler.remove_job(job_id)
                self.known_jobs.remove(job_id)
                logger.info(f"Removed sync schedule for job {job_id}")

    async def start_scheduler(self):
        """
        Starts the scheduler and the job refresher without blocking.
        """
        logger.info("Starting Stateful ABAC Scheduler (Embedded Mode)...")
        
        # Schedule the refresher to run every minute to pick up config changes
        self.scheduler.add_job(self.refresh_jobs, 'interval', seconds=60, id='config_refresher')
        
        # Initial load
        await self.refresh_jobs()
        
        self.scheduler.start()

    async def stop_scheduler(self):
        logger.info("Stopping Stateful ABAC Scheduler...")
        self.scheduler.shutdown()

    async def run_forever(self):
        """
        Starts the scheduler and blocks forever (for standalone usage).
        """
        await self.start_scheduler()
        
        # Keep alive
        try:
            while True:
                await asyncio.sleep(100)
        except (KeyboardInterrupt, asyncio.CancelledError):
            await self.stop_scheduler()

if __name__ == "__main__":
    # Configure logging for standalone mode
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    worker = SchedulerWorker()
    asyncio.run(worker.run_forever())
