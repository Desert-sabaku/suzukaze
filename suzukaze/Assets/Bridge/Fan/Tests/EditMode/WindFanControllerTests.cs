using System;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Suzukaze.Fan.Tests
{
    public class WindFanControllerTests
    {
        // Default layout, in FanOutput order: -135, -90, -45, 135, 90 and 45
        // degrees, 1.5 apart from the player.
        private const int LeftBack = 0;
        private const int LeftSide = 1;
        private const int LeftFront = 2;
        private const int RightBack = 3;
        private const int RightSide = 4;
        private const int RightFront = 5;

        private WindFanController controller;
        private Transform playerCamera;

        [SetUp]
        public void SetUp()
        {
            controller = new GameObject("WindFanController").AddComponent<WindFanController>();
            playerCamera = new GameObject("PlayerCamera").transform;
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(playerCamera.gameObject);
            Object.DestroyImmediate(controller.gameObject);
        }

        [Test]
        public void WindTravellingRightComesFromTheLeftFans()
        {
            byte[] output = controller.CalculateFanPower(playerCamera, Vector3.right, 1f);
            Assert.AreEqual(WindFanController.FanCount, output.Length);
            Assert.AreEqual(255, output[LeftSide]);
            // cos 45° for the left back and front fans.
            Assert.AreEqual(180, output[LeftBack]);
            Assert.AreEqual(180, output[LeftFront]);
            Assert.AreEqual(0, output[RightBack]);
            Assert.AreEqual(0, output[RightSide]);
            Assert.AreEqual(0, output[RightFront]);
        }

        [Test]
        public void WindBetweenTwoFansDrivesBothAtFullPower()
        {
            byte[] output = controller.CalculateFanPower(playerCamera, Vector3.forward, 1f);
            Assert.AreEqual(255, output[LeftBack]);
            Assert.AreEqual(255, output[RightBack]);
            Assert.AreEqual(0, output[LeftSide]);
            Assert.AreEqual(0, output[RightSide]);
            Assert.AreEqual(0, output[LeftFront]);
            Assert.AreEqual(0, output[RightFront]);
        }

        [Test]
        public void DefaultLayoutFollowsFanOutputOrder()
        {
            AssertNear(new Vector3(-1.5f, 0f, 0f), controller.GetFanPosition(playerCamera, LeftSide));
            AssertNear(new Vector3(1.5f, 0f, 0f), controller.GetFanPosition(playerCamera, RightSide));
            Assert.That(controller.GetFanPosition(playerCamera, LeftBack).z, Is.LessThan(0f));
            Assert.That(controller.GetFanPosition(playerCamera, LeftFront).z, Is.GreaterThan(0f));
            Assert.That(controller.GetFanPosition(playerCamera, RightBack).x, Is.GreaterThan(0f));
            Assert.That(controller.GetFanPosition(playerCamera, RightFront).z, Is.GreaterThan(0f));
        }

        [Test]
        public void SetWindBlowsUntilStopped()
        {
            controller.ReferenceCamera = playerCamera;
            controller.SetWind(Vector3.left, 1f);
            Assert.IsTrue(controller.IsBlowing);
            Assert.IsFalse(controller.IsPlayingPreset);
            Assert.AreEqual(255, controller.CurrentOutput[RightSide]);

            controller.StopWind();
            Assert.IsFalse(controller.IsBlowing);
            CollectionAssert.AreEqual(new byte[6], controller.CurrentOutput);
        }

        [Test]
        public void SetWindReplacesARunningPreset()
        {
            controller.ReferenceCamera = playerCamera;
            controller.PlayPreset(WindPreset.Strong);
            controller.SetWind(Vector3.left, 0.5f);
            Assert.IsFalse(controller.IsPlayingPreset);
            Assert.AreEqual(0.5f, controller.CurrentPower);
            controller.StopWind();
        }

        [Test]
        public void ZeroWindTurnsEveryFanOff() =>
            CollectionAssert.AreEqual(new byte[6], controller.CalculateFanPower(playerCamera, Vector3.zero, 1f));

        [Test]
        public void VerticalWindTurnsEveryFanOff() =>
            CollectionAssert.AreEqual(new byte[6], controller.CalculateFanPower(playerCamera, Vector3.up, 1f));

        [Test]
        public void OnlyTheDirectionOfTheWindMatters() =>
            CollectionAssert.AreEqual(
                controller.CalculateFanPower(playerCamera, Vector3.right, 1f),
                controller.CalculateFanPower(playerCamera, Vector3.right * 5f, 1f));

        [TestCase(0f, 0)]
        [TestCase(0.2f, 51)]
        [TestCase(1f, 255)]
        [TestCase(2f, 255)]
        [TestCase(-1f, 0)]
        public void PowerScalesTheOutput(float power, int expected) =>
            Assert.AreEqual(expected, controller.CalculateFanPower(playerCamera, Vector3.right, power)[LeftSide]);

        [Test]
        public void FansTurnWithTheCameraHeading()
        {
            playerCamera.SetPositionAndRotation(new Vector3(1f, 2f, 3f), Quaternion.Euler(0f, 90f, 0f));
            // Facing +X, the camera's left is +Z.
            AssertNear(new Vector3(1f, 2f, 4.5f), controller.GetFanPosition(playerCamera, LeftSide));
            AssertNear(new Vector3(1f, 2f, 1.5f), controller.GetFanPosition(playerCamera, RightSide));
            Assert.AreEqual(255, controller.CalculateFanPower(playerCamera, Vector3.right, 1f)[LeftSide]);
        }

        [TestCase(60f)]
        [TestCase(90f)]
        [TestCase(-90f)]
        public void FansStayLevelWhenTheCameraPitches(float pitch)
        {
            playerCamera.rotation = Quaternion.Euler(pitch, 0f, 0f);
            AssertNear(new Vector3(1.5f, 0f, 0f), controller.GetFanPosition(playerCamera, RightSide));
        }

        [Test]
        public void OnlyTheLevelPartOfTheWindReachesTheFans()
        {
            // Camera forward points 30° below the horizon, so cos 30° of it is level.
            playerCamera.rotation = Quaternion.Euler(30f, 0f, 0f);
            Assert.AreEqual(221, controller.CalculateFanPower(playerCamera, Vector3.forward, 1f)[LeftBack]);
        }

        [Test]
        public void MinimumOutputLiftsEveryBlowingFan()
        {
            var serialized = new SerializedObject(controller);
            serialized.FindProperty("minimumOutput").intValue = 100;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            byte[] weak = controller.CalculateFanPower(playerCamera, Vector3.right, 0.01f);
            Assert.That(weak[LeftSide], Is.InRange(100, 102));
            Assert.AreEqual(0, weak[RightSide]); // Fans the wind does not reach stay off.
            Assert.AreEqual(255, controller.CalculateFanPower(playerCamera, Vector3.right, 1f)[LeftSide]);
            CollectionAssert.AreEqual(new byte[6], controller.CalculateFanPower(playerCamera, Vector3.right, 0f));
        }

        [Test]
        public void MissingCameraIsRejected() =>
            Assert.Throws<ArgumentNullException>(() => controller.CalculateFanPower(null, Vector3.forward, 1f));

        [Test]
        public void TestResultChangesOnlyWhenApplied()
        {
            var serialized = new SerializedObject(controller);
            serialized.FindProperty("referenceCamera").objectReferenceValue = playerCamera;
            serialized.FindProperty("testWindDirection").vector3Value = Vector3.left;
            serialized.FindProperty("testWindPower").floatValue = 1f;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            controller.ApplyTestWind();
            serialized.Update();
            Assert.AreEqual(255, TestResult(serialized, RightSide));

            serialized.FindProperty("testWindDirection").vector3Value = Vector3.right;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            serialized.Update();
            Assert.AreEqual(255, TestResult(serialized, RightSide));

            controller.ApplyTestWind();
            serialized.Update();
            Assert.AreEqual(0, TestResult(serialized, RightSide));
            Assert.AreEqual(255, TestResult(serialized, LeftSide));
        }

        [Test]
        public void StopTestWindClearsTheResult()
        {
            controller.ReferenceCamera = playerCamera;
            controller.ApplyTestWind();
            controller.StopTestWind();
            var serialized = new SerializedObject(controller);
            for (int fan = 0; fan < WindFanController.FanCount; fan++)
                Assert.AreEqual(0, TestResult(serialized, fan));
            Assert.AreEqual(0f, serialized.FindProperty("appliedTestWindPower").floatValue);
        }

        private static int TestResult(SerializedObject serialized, int fan) =>
            serialized.FindProperty("testResult").GetArrayElementAtIndex(fan).intValue;

        private static void AssertNear(Vector3 expected, Vector3 actual) =>
            Assert.That(Vector3.Distance(expected, actual), Is.LessThan(1e-4f), $"expected {expected}, got {actual}");
    }
}
