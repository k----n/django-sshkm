from django.conf import settings
from django.utils import timezone
from django.utils.formats import localize
from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect, JsonResponse
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.core.exceptions import ObjectDoesNotExist

import celery
from celery import uuid
from celery.result import AsyncResult

from sshkm.tasks import ScheduleDeployKeys
from sshkm.views.deploy import DeployKeys, GetHostKeys

from sshkm.models import Host, Setting, Permission
from sshkm.forms import HostForm


@login_required
def HostList(request):
    hosts = Host.objects.order_by('name')

    # if hosts are created check if public/private keys are uploaded to make deployment possible
    keys = Setting.objects.filter(name__in=['MasterKeyPrivate', 'MasterKeyPublic']).count()
    if hosts and keys != 2:
        messages.add_message(request, messages.WARNING, "To be able to deploy keys to your hosts please navigate to the settings page and upload your master private and public key (as user with Admin priviledges).")

    context = {'hosts': hosts}
    return render(request, 'sshkm/host/list.html', context)

@login_required
def HostState(request):
    if request.is_ajax():
        if request.GET['id']:
            host = Host.objects.get(id=request.GET['id'])
            data = {"status": host.status, "last_status": localize(host.last_status)}
    else:
        data = {"status": None, "last_status": None}

    return JsonResponse(data)

@login_required
def HostDetail(request):
    if request.method == 'GET' and 'id' in request.GET:
        host = get_object_or_404(Host, pk=request.GET['id'])
        hostform = HostForm(instance=host)
        permissions = Permission.objects.filter(host_id=request.GET['id'])
        return render(request, 'sshkm/host/detail.html', {
            'hostform': hostform,
            'permissions': permissions,
        })
    else:
        hostform = HostForm()
        return render(request, 'sshkm/host/detail.html', {
            'hostform': hostform,
        })

@login_required
def HostDelete(request):
    try:
        if request.POST.get('id_multiple') is not None:
            Host.objects.filter(id__in=request.POST.getlist('id_multiple')).delete()
            messages.add_message(request, messages.SUCCESS, "Hosts deleted")
        else:
            host = Host.objects.get(id=request.GET['id'])
            delete = Host(id=request.GET['id']).delete()
            messages.add_message(request, messages.SUCCESS, "Host " + host.name + " deleted")
    except ObjectDoesNotExist as e:
        messages.add_message(request, messages.ERROR, "The host could not be deleted")
    except Exception as e:
        messages.add_message(request, messages.ERROR, "The host could not be deleted")

    return HttpResponseRedirect(reverse('HostList'))

@login_required
def HostSave(request):
    try:
        if request.POST.get('id') is not None:
            hostInstance = Host.objects.get(id=request.POST.get('id'))
            host = HostForm(request.POST, instance=hostInstance)
        else:
            host = HostForm(request.POST)
        host.save()
        messages.add_message(request, messages.SUCCESS, "Host " + request.POST.get('name') + " sucessfully saved")
    except IntegrityError as e:
        messages.add_message(request, messages.ERROR, "The host could not be saved.")
    except Exception as e:
        messages.add_message(request, messages.ERROR, "The host could not be saved")

    return HttpResponseRedirect(reverse('HostList'))

@login_required
def HostDeploy(request):
    if settings.SSHKM_DEMO is False:
        try:
            if request.POST.get('id_multiple') is not None:
                for host in request.POST.getlist('id_multiple'):
                    hoststatus = Host.objects.get(id=host)
                    hoststatus.status = 'PENDING'
                    hoststatus.save()
                    deploy = ScheduleDeployKeys.apply_async([host])
                messages.add_message(request, messages.INFO, "Multiple host deployment initiated")
            else:
                host = Host.objects.get(id=request.GET['id'])
                try:
                    deploy = DeployKeys(GetHostKeys(request.GET['id']), request.GET['id'])
                    if deploy == "NTD":
                        messages.add_message(request, messages.INFO, "Nothing to deploy for Host " + host.name)
                    else:
                        messages.add_message(request, messages.SUCCESS, "Host " + host.name + " deployed")
                except:
                    messages.add_message(request, messages.ERROR, "Host " + host.name + " could not be deployed")
        except Exception as e:
            if str(e) == "[Errno 111] Connection refused":
                messages.add_message(request, messages.ERROR, "The host(s) could not be deployed. Celery is not running.")
            else:
                messages.add_message(request, messages.ERROR, "The host(s) could not be deployed")
    else:
        messages.add_message(request, messages.INFO, "Deployment is disabled in demo mode.")

    return HttpResponseRedirect(reverse('HostList'))
