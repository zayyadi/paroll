from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from .models.payroll import IOU
from .forms import IOUCreateForm, IOUUpdateForm, IOUDeleteForm


def iou_list(request):
    ious = IOU.objects.all()
    return render(request, "iou/iou_list.html", {"ious": ious})


def iou_detail(request, pk):
    iou = get_object_or_404(IOU, pk=pk)
    return render(request, "iou/iou_detail.html", {"iou": iou})


def iou_create(request):
    if request.method == "POST":
        form = IOUCreateForm(request.POST)
        if form.is_valid():
            iou = form.save()
            messages.success(request, "IOU created successfully.")
            return redirect("payroll:iou_detail", pk=iou.pk)
        else:
            messages.error(request, "There was an error creating the IOU.")
    else:
        form = IOUCreateForm()
    return render(request, "iou/iou_create.html", {"form": form})


def iou_update(request, pk):
    iou = get_object_or_404(IOU, pk=pk)
    if request.method == "POST":
        form = IOUUpdateForm(request.POST, instance=iou)
        if form.is_valid():
            form.save()
            messages.success(request, "IOU updated successfully.")
            return redirect("payroll:iou_detail", pk=iou.pk)
        else:
            messages.error(request, "There was an error updating the IOU.")
    else:
        form = IOUUpdateForm(instance=iou)
    return render(request, "iou/iou_update.html", {"form": form, "iou": iou})


def iou_delete(request, pk):
    iou = get_object_or_404(IOU, pk=pk)
    if request.method == "POST":
        form = IOUDeleteForm(request.POST)
        if form.is_valid():
            iou.delete()
            messages.success(request, "IOU deleted successfully.")
            return redirect("payroll:iou_list")
        else:
            messages.error(request, "There was an error deleting the IOU.")
    else:
        form = IOUDeleteForm()
    return render(request, "iou/iou_delete.html", {"form": form, "iou": iou})
