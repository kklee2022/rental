from celery import shared_task

from core.tasks import TenantTask

from .services import release_expired_holds


@shared_task(base=TenantTask, ignore_result=True)
def release_expired_reservation_holds(**kwargs):
    """Release abandoned short-lived holds for one tenant."""

    return release_expired_holds()
