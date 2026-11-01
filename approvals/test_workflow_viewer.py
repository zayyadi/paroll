from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from company.models import Company
from .models import ApprovalPolicy, ApprovalRequest
from .registry import ApprovalAction, _actions, register_action
from .services import cancel_approval, decide_approval, submit_approval
from .workflow import document_workflows, workflow_context


class WorkflowViewerTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Viewer company')
        self.other = Company.objects.create(name='Other viewer company')
        User = get_user_model()
        self.maker = User.objects.create_user(email='maker@viewer.test', company=self.company)
        self.checker = User.objects.create_user(email='checker@viewer.test', first_name='First', last_name='Checker', company=self.company)
        self.second = User.objects.create_user(email='second@viewer.test', company=self.company)
        self.outsider = User.objects.create_user(email='outsider@viewer.test', company=self.other)
        permission = Permission.objects.get(content_type__app_label='company', codename='change_company')
        for user in (self.maker, self.checker, self.second):
            user.user_permissions.add(permission)
        self.key = 'test.viewer'
        register_action(ApprovalAction(
            key=self.key, model_label='users.CustomUser', permission='company.change_company',
            requester=lambda source: source, apply=lambda *args: None,
        ))
        self.addCleanup(lambda: _actions.pop(self.key, None))
        self.policy = ApprovalPolicy.objects.create(company=self.company, action=self.key, stages=[
            {'name': 'Finance review', 'permission': 'company.change_company', 'approver_ids': [self.checker.pk]},
            {'name': 'Final review', 'permission': 'company.change_company', 'approver_ids': [self.second.pk]},
        ])

    def submit(self):
        return submit_approval(source=self.maker, action=self.key, requester=self.maker)

    def render_viewer(self, user, **context):
        request = RequestFactory().get('/')
        request.user = user
        return Template('{% load approval_workflow %}{% approval_workflow %}').render(Context({'request': request, **context})).strip()

    def test_next_approver_and_completed_decisions_follow_snapshot(self):
        approval = self.submit()
        self.policy.stages = [{'name': 'Changed policy', 'permission': 'company.change_company', 'approver_ids': [self.maker.pk]}]
        self.policy.save()
        workflow = workflow_context(approval, self.maker)
        self.assertEqual(workflow['next_approvers'], ['First Checker'])
        self.assertEqual(workflow['stages'][1]['name'], 'Final review')
        approval = decide_approval(approval=approval, actor=self.checker)
        workflow = workflow_context(approval, self.maker)
        self.assertEqual(workflow['next_approvers'], [self.second.email])
        self.assertEqual(workflow['stages'][0]['state'], 'Approved')
        self.assertEqual(workflow['stages'][0]['actor_name'], 'First Checker')
        approval = decide_approval(approval=approval, actor=self.second)
        workflow = workflow_context(approval, self.maker)
        self.assertFalse(workflow['waiting'])
        self.assertEqual(workflow['next_approvers'], [])
        self.assertTrue(all(s['state'] == 'Approved' for s in workflow['stages']))

    def test_permission_routing_excludes_maker_and_prior_checkers(self):
        self.policy.stages = [{'permission': 'company.change_company'}] * 2
        self.policy.save()
        approval = self.submit()
        self.assertEqual(set(workflow_context(approval, self.maker)['next_approvers']), {'First Checker', self.second.email})
        approval = decide_approval(approval=approval, actor=self.checker)
        self.assertEqual(workflow_context(approval, self.maker)['next_approvers'], [self.second.email])

    def test_beneficiary_and_inactive_assignee_cannot_be_next(self):
        from dataclasses import replace
        _actions[self.key] = replace(_actions[self.key], beneficiaries=lambda source: [self.checker.pk])
        approval = self.submit()
        self.assertEqual(workflow_context(approval, self.maker)['next_approvers'], [])
        self.checker.is_active = False
        self.checker.save()
        html = self.render_viewer(self.maker, object=self.maker)
        self.assertIn('No eligible approver available', html)
        self.assertIn('Unavailable approver', html)

    def test_rejection_does_not_mark_unreached_stages_approved(self):
        approval = decide_approval(approval=self.submit(), actor=self.checker, decision='REJECT', comment='Review again')
        workflow = workflow_context(approval, self.maker)
        self.assertEqual([s['state'] for s in workflow['stages']], ['Rejected', 'Not reached'])
        self.assertFalse(workflow['waiting'])

    def test_cancellation_has_no_next_approver(self):
        approval = cancel_approval(approval=self.submit(), actor=self.maker, reason='Revise')
        workflow = workflow_context(approval, self.maker)
        self.assertEqual(workflow['next_approvers'], [])
        self.assertEqual(workflow['stages'][0]['state'], 'Not reached')

    def test_cross_company_and_anonymous_viewers_get_no_workflow(self):
        approval = self.submit()
        self.assertIsNone(workflow_context(approval, self.outsider))
        self.assertEqual(document_workflows(self.maker, self.outsider), [])
        self.assertEqual(self.render_viewer(self.outsider, object=self.maker), '')
        self.assertEqual(self.render_viewer(AnonymousUser(), object=self.maker), '')

    def test_source_visibility_is_respected(self):
        from dataclasses import replace
        approval = self.submit()
        _actions[self.key] = replace(_actions[self.key], source_visibility=lambda source, user: False)
        self.assertIsNone(workflow_context(approval, self.maker))
        self.assertEqual(self.render_viewer(self.maker, object=self.maker), '')

    def test_draft_preview_is_read_only_and_has_no_request_link(self):
        html = self.render_viewer(self.maker, object=self.maker)
        self.assertIn('Not submitted', html)
        self.assertIn('Finance review', html)
        self.assertIn('First Checker', html)
        self.assertNotIn('View approval request and history', html)
        self.assertEqual(ApprovalRequest.objects.count(), 0)

    def test_document_and_request_context_render_same_next_approver(self):
        approval = self.submit()
        for context in ({'object': self.maker}, {'approval': approval}):
            html = self.render_viewer(self.maker, **context)
            self.assertIn('Next: First Checker', html)
            self.assertIn('aria-current="step"', html)
            self.assertIn('Final review', html)

    def test_moved_source_cannot_disclose_old_company_workflow(self):
        approval = self.submit()
        self.maker.company = self.other
        self.maker.save()
        self.assertIsNone(workflow_context(approval, self.checker))

    def test_dashboard_context_has_no_viewer(self):
        self.assertEqual(self.render_viewer(self.maker, company=self.company), '')

    def test_designated_approver_needs_no_permission_but_must_select_company(self):
        self.checker.user_permissions.clear()
        approval = self.submit()
        self.assertEqual(workflow_context(approval, self.maker)['next_approvers'], ['First Checker'])
        self.checker.active_company = self.other
        self.checker.save()
        self.assertEqual(workflow_context(approval, self.maker)['next_approvers'], [])

    def test_function_view_document_alias_is_detected(self):
        self.submit()
        html = self.render_viewer(self.maker, pay_period=self.maker)
        self.assertIn('Next: First Checker', html)

    def test_completed_proposal_is_visible_on_resulting_document(self):
        from company.models import ActionProposal
        key = 'test.viewer.proposal'
        def apply(source, actor, payload):
            source.status = 'APPLIED'
            source.result_type = self.maker._meta.label_lower
            source.result_id = self.maker.pk
            source.save(update_fields=['status', 'result_type', 'result_id'])
        register_action(ApprovalAction(
            key=key, model_label='company.ActionProposal', permission='company.change_company',
            requester=lambda source: source.created_by, apply=apply,
        ))
        self.addCleanup(lambda: _actions.pop(key, None))
        proposal = ActionProposal.objects.create(company=self.company, action=key,
            parameters={}, created_by=self.maker, request_key='viewer-result')
        approval = submit_approval(source=proposal, action=key, requester=self.maker)
        decide_approval(approval=approval, actor=self.checker)
        workflows = document_workflows(self.maker, self.maker)
        self.assertEqual(len(workflows), 1)
        self.assertEqual(workflows[0]['approval'].pk, approval.pk)
        self.assertFalse(workflows[0]['waiting'])

    def test_document_reader_sees_routing_without_private_request_link(self):
        reader = get_user_model().objects.create_user(email='reader@viewer.test', company=self.company)
        reader.user_permissions.add(Permission.objects.get(
            content_type__app_label='users', codename='view_customuser'))
        self.submit()
        workflow = document_workflows(self.maker, reader)[0]
        self.assertEqual(workflow['next_approvers'], ['First Checker'])
        self.assertFalse(workflow['can_open_request'])
        html = self.render_viewer(reader, object=self.maker)
        self.assertIn('Next: First Checker', html)
        self.assertNotIn('View approval request and history', html)

    def test_requester_as_only_assigned_approver_has_explicit_explanation(self):
        self.policy.stages = [{'permission': 'company.change_company', 'approver_ids': [self.maker.pk]}]
        self.policy.save()
        approval = self.submit()
        workflow = workflow_context(approval, self.maker)
        self.assertEqual(workflow['next_approvers'], [])
        self.assertIn('cannot approve their own request', workflow['blocked_reason'])
        html = self.render_viewer(self.maker, approval=approval)
        self.assertIn('The requester is the only assigned approver', html)
