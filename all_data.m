close all
clear all
clc
% %绘制赤经赤纬散点图，无意义。。。舍弃
% %system('copy D:\00adias\exe\DATA\radecfig4003\*.dat D:\00adias\exe\DATA\radecfig4003\alldata.dat /y')
% a=load('D:\00adias\exe\DATA\alldata.dat');
% t0=a(:,3);
% ra0=a(:,14);
% de0=a(:,15);
% 
% figure(1)
% plot(ra0,de0, 'k.');
% xlabel('\Delta \alpha (")');
% ylabel('\Delta \delta (")');
% %axis([0-0.155 0.155,-0.155 0.155])
% hold on
% grid on
% stop
% 适用于多颗天然卫星目标
%==============================1
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2013101.dat');%2013年U1
t11=a(:,3);
ra11=a(:,14);
de11=a(:,15);
expt11=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2013102.dat');%%2013年U2
t12=a(:,3);
ra12=a(:,14);
de12=a(:,15);
expt12=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2013103.dat');%%2013年U3
t13=a(:,3);
ra13=a(:,14);
de13=a(:,15);
expt13=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2013104.dat');%%2013年U4
t14=a(:,3);
ra14=a(:,14);
de14=a(:,15);
expt14=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2013105.dat');%%2013年U5
t15=a(:,3);
ra15=a(:,14);
de15=a(:,15);
expt15=a(:,20);
%==============================2
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2014091.dat');%2014年U1
t21=a(:,3);
ra21=a(:,14);
de21=a(:,15);
expt21=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2014092.dat');%2014年U2
t22=a(:,3);
ra22=a(:,14);
de22=a(:,15);
expt22=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2014093.dat');%2014年U3
t23=a(:,3);
ra23=a(:,14);
de23=a(:,15);
expt23=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2014094.dat');%2014年U4
t24=a(:,3);
ra24=a(:,14);
de24=a(:,15);
expt24=a(:,20);
a=0;
% a=load('D:\00adias\exe\DATA\Uranus5\2014095.dat');%2014年U5
% t25=a(:,3);
% ra25=a(:,14);
% de25=a(:,15);
% expt25=a(:,20);
%==============================3
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2017091.dat');%2017年U1
t31=a(:,3);
ra31=a(:,14);
de31=a(:,15);
expt31=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2017092.dat');%2017年U2
t32=a(:,3);
ra32=a(:,14);
de32=a(:,15);
expt32=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2017093.dat');%2017年U3
t33=a(:,3);
ra33=a(:,14);
de33=a(:,15);
expt33=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2017094.dat');%2017年U4
t34=a(:,3);
ra34=a(:,14);
de34=a(:,15);
expt34=a(:,20);
a=0
a=load('D:\00adias\exe\DATA\Uranus5\2017095.dat');%2017年U5
t35=a(:,3);
ra35=a(:,14);
de35=a(:,15);
expt35=a(:,20);
%==============================4
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2019091.dat');%2019年U1
t41=a(:,3);
ra41=a(:,14);
de41=a(:,15);
expt41=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2019092.dat');%2019年U2
t42=a(:,3);
ra42=a(:,14);
de42=a(:,15);
expt42=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2019093.dat');%2019年U3
t43=a(:,3);
ra43=a(:,14);
de43=a(:,15);
expt43=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2019094.dat');%2019年U4
t44=a(:,3);
ra44=a(:,14);
de44=a(:,15);
expt44=a(:,20);
a=0
a=load('D:\00adias\exe\DATA\Uranus5\2019095.dat');%2019年U5
t45=a(:,3);
ra45=a(:,14);
de45=a(:,15);
expt45=a(:,20);
%==============================5
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2020101.dat');%2020年10月U1
t51=a(:,3);
ra51=a(:,14);
de51=a(:,15);
expt51=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2020102.dat');%2020年10月U2
t52=a(:,3);
ra52=a(:,14);
de52=a(:,15);
expt52=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2020103.dat');%2020年10月U3
t53=a(:,3);
ra53=a(:,14);
de53=a(:,15);
expt53=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2020104.dat');%2020年10月U4
t54=a(:,3);
ra54=a(:,14);
de54=a(:,15);
expt54=a(:,20);
a=0
a=load('D:\00adias\exe\DATA\Uranus5\2020105.dat');%2020年10月U5
t55=a(:,3);
ra55=a(:,14);
de55=a(:,15);
expt55=a(:,20);
%==============================6
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2020111.dat');%2020年11月U1
t61=a(:,3);
ra61=a(:,14);
de61=a(:,15);
expt61=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2020112.dat');%2020年11月U2
t62=a(:,3);
ra62=a(:,14);
de62=a(:,15);
expt62=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2020113.dat');%2020年11月U3
t63=a(:,3);
ra63=a(:,14);
de63=a(:,15);
expt63=a(:,20);
a=0;
a=load('D:\00adias\exe\DATA\Uranus5\2020114.dat');%2020年11月U4
t64=a(:,3);
ra64=a(:,14);
de64=a(:,15);
expt64=a(:,20);
a=0
a=load('D:\00adias\exe\DATA\Uranus5\2020115.dat');%2020年11月U5
t65=a(:,3);
ra65=a(:,14);
de65=a(:,15);
expt65=a(:,20);
% %==============================7
% a=0;
% a=load('D:\00adias\exe\DATA\Uranus5\2014091.dat');%2009
% t71=a(:,3);
% ra71=a(:,14);
% de71=a(:,15);
% expt71=a(:,20);
% a=0;
% a=load('D:\00adias\exe\DATA\Uranus5\2014092.dat');%2009
% t72=a(:,3);
% ra72=a(:,14);
% de72=a(:,15);
% expt72=a(:,20);
% a=0;
% a=load('D:\00adias\exe\DATA\Uranus5\2014093.dat');%2009
% t73=a(:,3);
% ra73=a(:,14);
% de73=a(:,15);
% expt73=a(:,20);
% a=0;
% a=load('D:\00adias\exe\DATA\Uranus5\2014094.dat');%2009
% t74=a(:,3);
% ra74=a(:,14);
% de74=a(:,15);
% expt74=a(:,20);
% a=0
% % a=load('D:\00adias\exe\DATA\Uranus5\2014095.dat');%2009
% % t75=a(:,3);
% % ra75=a(:,14);
% % de75=a(:,15);
% % expt75=a(:,20);


figure(1)
subplot(6,2,1)
plot(t11, ra11, 'r.','MarkerSize',6);
hold on
plot(t12+0.15, ra12, 'b.','MarkerSize',6);
hold on
plot(t13+0.3, ra13, 'k.','MarkerSize',6);
hold on
plot(t14+0.45, ra14, 'g.','MarkerSize',6);
hold on
plot(t15+0.6, ra15, 'c.','MarkerSize',6);
hold on
%set(gca,'linewidth',0.7)

xlabel('Time in day (UTC) in Oct. 2013');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,2)
plot(t11, de11, 'r.','MarkerSize',6);
hold on
plot(t12+0.15, de12, 'b.','MarkerSize',6);
hold on
plot(t13+0.3, de13, 'k.','MarkerSize',6);
hold on
plot(t14+0.45, de14, 'g.','MarkerSize',6);
hold on
plot(t15+0.6, de15, 'c.','MarkerSize',6);
hold on
xlabel('Time in day (UTC) in Oct. 2013');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,3)
plot(t21, ra21, 'r.','MarkerSize',6);
hold on
plot(t22+0.15, ra22, 'b.','MarkerSize',6);
hold on
plot(t23+0.3, ra23, 'k.','MarkerSize',6);
hold on
plot(t24+0.45, ra24, 'g.','MarkerSize',6);
hold on
xlabel('Time in day (UTC) in Sep. 2014');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,4)
plot(t21, de21, 'r.','MarkerSize',6);
hold on
plot(t22+0.15, de22, 'b.','MarkerSize',6);
hold on
plot(t23+0.3, de23, 'k.','MarkerSize',6);
hold on
plot(t24+0.45, de24, 'g.','MarkerSize',6);
hold on
xlabel('Time in day (UTC) in Sep. 2014');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,5)
plot(t31, ra31, 'r.','MarkerSize',6);
hold on
plot(t32+0.15, ra32, 'b.','MarkerSize',6);
hold on
plot(t33+0.3, ra33, 'k.','MarkerSize',6);
hold on
plot(t34+0.45, ra34, 'g.','MarkerSize',6);
hold on
plot(t35+0.6, ra35, 'c.','MarkerSize',6);
hold on
xlabel('Time in day (UTC) in Sep. 2017');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,6)
plot(t31, de31, 'r.','MarkerSize',6);
hold on
plot(t32+0.15, de32, 'b.','MarkerSize',6);
hold on
plot(t33+0.3, de33, 'k.','MarkerSize',6);
hold on
plot(t34+0.45, de34, 'g.','MarkerSize',6);
hold on
plot(t35+0.6, de35, 'c.','MarkerSize',6);
hold on
xlabel('Time in day (UTC) in Sep. 2017');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,7)
plot(t41, ra41, 'r.','MarkerSize',6);
hold on
plot(t42+0.15, ra42, 'b.','MarkerSize',6);
hold on
plot(t43+0.3, ra43, 'k.','MarkerSize',6);
hold on
plot(t44+0.45, ra44, 'g.','MarkerSize',6);
hold on
plot(t45+0.6, ra45, 'c.','MarkerSize',6);
hold on
xlabel('Time in day (UTC) in Sep. 2019');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,8)
plot(t41, de41, 'r.','MarkerSize',6);
hold on
plot(t42+0.15, de42, 'b.','MarkerSize',6);
hold on
plot(t43+0.3, de43, 'k.','MarkerSize',6);
hold on
plot(t44+0.45, de44, 'g.','MarkerSize',6);
hold on
plot(t45+0.6, de45, 'c.','MarkerSize',6);
hold on
xlabel('Time in day (UTC) in Sep. 2019');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,9)
plot(t51, ra51, 'r.','MarkerSize',6);
hold on
plot(t52+0.15, ra52, 'b.','MarkerSize',6);
hold on
plot(t53+0.3, ra53, 'k.','MarkerSize',6);
hold on
plot(t54+0.45, ra54, 'g.','MarkerSize',6);
hold on
plot(t55+0.6, ra55, 'c.','MarkerSize',6);
hold on
legend('UⅠ','UⅡ','UⅢ','UⅣ','UⅤ')
xlabel('Time in day (UTC) in Oct. 2020');
ylabel('\Delta \alpha cos\delta(")');
hold on
grid on

subplot(6,2,10)
plot(t51, de51, 'r.','MarkerSize',6);
hold on
plot(t52+0.15, de52, 'b.','MarkerSize',6);
hold on
plot(t53+0.3, de53, 'k.','MarkerSize',6);
hold on
plot(t54+0.45, de54, 'g.','MarkerSize',6);
hold on
plot(t55+0.6, de55, 'c.','MarkerSize',6);
hold on
%legend('UⅠ','UⅡ','UⅢ','UⅣ','UⅤ')
xlabel('Time in day (UTC) in Oct. 2020');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,11)
plot(t61, ra61, 'r.','MarkerSize',6);
hold on
plot(t62+0.15, ra62, 'b.','MarkerSize',6);
hold on
plot(t63+0.3, ra63, 'k.','MarkerSize',6);
hold on
plot(t64+0.45, ra64, 'g.','MarkerSize',6);
hold on
plot(t65+0.6, ra65, 'c.','MarkerSize',6);
hold on
xlabel('Time in day (UTC) in Nov. 2020');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,12)
plot(t61, de61, 'r.','MarkerSize',6);
hold on
plot(t62+0.15, de62, 'b.','MarkerSize',6);
hold on
plot(t63+0.3, de63, 'k.','MarkerSize',6);
hold on
plot(t64+0.45, de64, 'g.','MarkerSize',6);
hold on
plot(t65+0.6, de65, 'c.','MarkerSize',6);
hold on
xlabel('Time in day (UTC) in Nov. 2020');
ylabel('\Delta \delta (")');
hold on
grid on

% subplot(6,2,13)
% plot(t71, ra71, 'r.','MarkerSize',6);
% hold on
% plot(t72+0.15, ra72, 'b.','MarkerSize',6);
% hold on
% plot(t73+0.3, ra73, 'k.','MarkerSize',6);
% hold on
% plot(t74+0.45, ra74, 'g.','MarkerSize',6);
% hold on
% xlabel('Time in day (UTC) in Sep. 2014');
% ylabel('\Delta \alpha cos\delta (")');
% hold on
% grid on
% 
% subplot(6,2,14)
% plot(t71, de71, 'r.','MarkerSize',6);
% hold on
% plot(t72+0.15, de72, 'b.','MarkerSize',6);
% hold on
% plot(t73+0.3, de73, 'k.','MarkerSize',6);
% hold on
% plot(t74+0.45, de74, 'g.','MarkerSize',6);
% hold on
% xlabel('Time in day (UTC) in Sep. 2014');
% ylabel('\Delta \delta (")');
% hold on
% grid on

stop

figure(1)

subplot(6,2,1)
plot(t11, ra11, 'r.');
hold on
plot(t12, ra12, 'b.');
hold on
plot(t13, ra13, 'c.');
hold on
plot(t14, ra15, 'g.');
hold on
plot(t16, ra17, 'k.');
hold on


legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Oct. 2013');
ylabel('O-C (")');
hold on

grid on

subplot(6,2,2)
plot(t4, ra4, 'r.');%200608
hold on
plot(t4+0.2, de4, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Oct. 2013');
ylabel('O-C (")');
hold on
grid on

subplot(6,2,3)
plot(t5, ra5, 'r.');%200609
hold on
plot(t5+0.2, de5, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2014');
ylabel('O-C (")');
hold on
grid on


subplot(6,2,4)
plot(t6, ra6, 'r.');%200708
hold on
plot(t6+0.2, de6, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2014');
ylabel('O-C (")');
hold on
grid on

subplot(6,2,5)
plot(t7, ra7, 'r.');%200709
hold on
plot(t7+0.2, de7, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2017');
ylabel('O-C (")');
hold on
grid on

subplot(6,2,6)
plot(t8, ra8, 'r.');%200808
hold on
plot(t8+0.2, de8, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2017');
ylabel('O-C (")');
hold on
grid on

subplot(6,2,7)
plot(t9, ra9, 'r.');%200809
hold on
plot(t9+0.2, de9, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2019');
ylabel('O-C (")');
hold on
grid on

subplot(6,2,8)
plot(t10, ra10, 'r.');%200908
hold on
plot(t10+0.2, de10, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2019');
ylabel('O-C (")');
hold on
grid on

subplot(6,2,9)
plot(t11, ra11, 'r.');%201008
hold on
plot(t11+0.2, de11, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Aug. 2010');
ylabel('O-C (")');
hold on
grid on

subplot(6,2,10)
plot(t12, ra12, 'r.');%201009
hold on
plot(t12+0.2, de12, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2010');
ylabel('O-C (")');
hold on
grid on

subplot(6,2,11)
plot(t13, ra13, 'r.');%201109
hold on
plot(t13+0.2, de13, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2011');
ylabel('O-C (")');
hold on
grid on

subplot(6,2,12)
plot(t14, ra14, 'r.');%201409
hold on
plot(t14+0.2, de14, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2014');
ylabel('O-C (")');
hold on
grid on

subplot(6,2,13)
plot(t14, ra14, 'r.');%201409
hold on
plot(t14+0.2, de14, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2014');
ylabel('O-C (")');
hold on
grid on


subplot(6,2,14)
plot(t14, ra14, 'r.');%201409
hold on
plot(t14+0.2, de14, 'b.');
%legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Sep. 2014');
ylabel('O-C (")');
hold on
grid on

stop

%=================================================================

figure(1)
subplot(6,2,1)
plot(t1, ra1, 'k.');
hold on
plot(t1, de1, 'k.');
legend('\Delta \alpha cos\delta (")','\Delta \delta (")')
xlabel('Time in day (UTC) in Aug. 1996');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,2)
plot(t1, de1, 'k.');
xlabel('Time in day (UTC) in Aug. 1996');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,3)
plot(t2, ra2, 'k.');
xlabel('Time in day (UTC) in Aug. 2003');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,4)
plot(t2, de2, 'k.');
xlabel('Time in day (UTC) in Aug. 2003');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,5)
plot(t3, ra3, 'k.');
xlabel('Time in day (UTC) in Sep. 2005');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,6)
plot(t3, de3, 'k.');
xlabel('Time in day (UTC) in Sep. 2005');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,7)
plot(t4, ra4, 'k.');
xlabel('Time in day (UTC) in Aug. 2006');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,8)
plot(t4, de4, 'k.');
xlabel('Time in day (UTC) in Aug. 2006');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,9)
plot(t5, ra5, 'k.');
xlabel('Time in day (UTC) in Sep. 2006');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,10)
plot(t5, de5, 'k.');
xlabel('Time in day (UTC) in Sep. 2006');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,11)
plot(t6, ra6, 'k.');
xlabel('Time in day (UTC) in Aug. 2007');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,12)
plot(t6, de6, 'k.');
xlabel('Time in day (UTC) in Aug. 2007');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,13)
plot(t7, ra7, 'k.');
xlabel('Time in day (UTC) in Sep. 2007');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,14)
plot(t7, de7, 'k.');
xlabel('Time in day (UTC) in Sep. 2007');
ylabel('\Delta \delta (")');
hold on
grid on

%=====================
figure(2)
subplot(6,2,1)
plot(t8, ra8, 'k.');
xlabel('Time in day (UTC) in Aug. 2008');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,2)
plot(t8, de8, 'k.');
xlabel('Time in day (UTC) in Aug. 2008');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,3)
plot(t9, ra9, 'k.');
xlabel('Time in day (UTC) in Sep. 2008');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,4)
plot(t9, de9, 'k.');
xlabel('Time in day (UTC) in Sep. 2008');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,5)
plot(t10, ra10, 'k.');
xlabel('Time in day (UTC) in Aug. 2009');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,6)
plot(t10, de10, 'k.');
xlabel('Time in day (UTC) in Aug. 2009');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,7)
plot(t11, ra11, 'k.');
xlabel('Time in day (UTC) in Aug. 2010');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,8)
plot(t11, de11, 'k.');
xlabel('Time in day (UTC) in Aug. 2010');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,9)
plot(t12, ra12, 'k.');
xlabel('Time in day (UTC) in Sep. 2010');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,10)
plot(t12, de12, 'k.');
xlabel('Time in day (UTC) in Sep. 2010');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,11)
plot(t13, ra13, 'k.');
xlabel('Time in day (UTC) in Sep. 2011');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,12)
plot(t13, de13, 'k.');
xlabel('Time in day (UTC) in Sep. 2011');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,13)
plot(t14, ra14, 'k.');
xlabel('Time in day (UTC) in Sep. 2014');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,14)
plot(t14, de14, 'k.');
xlabel('Time in day (UTC) in Sep. 2014');
ylabel('\Delta \delta (")');
hold on
grid on

%============
figure(3)
subplot(6,2,1)
plot(t1, expt1, 'k.');
xlabel('Time in day (UTC) in Aug. 1996');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,2)
plot(t2, expt2, 'k.');
xlabel('Time in day (UTC) in Aug. 1996');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,3)
plot(t3, expt3, 'k.');
xlabel('Time in day (UTC) in Aug. 2003');
ylabel('\Delta \alpha cos\delta (")');
hold on
grid on

subplot(6,2,4)
plot(t4, expt4, 'k.');
xlabel('Time in day (UTC) in Aug. 2003');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,5)
plot(t5, expt5, 'k.');
xlabel('Time in day (UTC) in Sep. 2005');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,6)
plot(t6, expt6, 'k.');
xlabel('Time in day (UTC) in Sep. 2005');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,7)
plot(t7, expt7, 'k.');
xlabel('Time in day (UTC) in Aug. 2006');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,8)
plot(t8, expt8, 'k.');
xlabel('Time in day (UTC) in Aug. 2006');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,9)
plot(t9, expt9, 'k.');
xlabel('Time in day (UTC) in Sep. 2006');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,10)
plot(t10, expt10, 'k.');
xlabel('Time in day (UTC) in Sep. 2006');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,11)
plot(t11, expt11, 'k.');
xlabel('Time in day (UTC) in Aug. 2007');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,12)
plot(t12, expt12, 'k.');
xlabel('Time in day (UTC) in Aug. 2007');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,13)
plot(t13, expt13, 'k.');
xlabel('Time in day (UTC) in Sep. 2007');
ylabel('\Delta \delta (")');
hold on
grid on

subplot(6,2,14)
plot(t14, expt14, 'k.');
xlabel('Time in day (UTC) in Sep. 2007');
ylabel('\Delta \delta (")');
hold on
grid on


% fprintf('a+b=');disp(c);
% fprintf('Aug.2003 &');disp(day200308);fprintf('&');disp(sum200308);fprintf('&');disp(mean200308ra);fprintf('&');disp(mean200308de);fprintf('&');disp(std200308ra);fprintf('&');disp(std200308de);fprintf('\\')
fprintf('Sep.2005 &');disp(day200509);fprintf('&');disp(sum200509);fprintf('&');disp(mean200509ra);fprintf('&');disp(mean200509de);fprintf('&');disp(std200509ra);fprintf('&');disp(std200509de);fprintf('\\')
fprintf('Aug.2006 &');disp(day200608);fprintf('&');disp(sum200608);fprintf('&');disp(mean200608ra);fprintf('&');disp(mean200608de);fprintf('&');disp(std200608ra);fprintf('&');disp(std200608de);fprintf('\\')
fprintf('Sep.2006 &');disp(day200609);fprintf('&');disp(sum200609);fprintf('&');disp(mean200609ra);fprintf('&');disp(mean200609de);fprintf('&');disp(std200609ra);fprintf('&');disp(std200609de);fprintf('\\')
fprintf('Aug.2007 &');disp(day200708);fprintf('&');disp(sum200708);fprintf('&');disp(mean200708ra);fprintf('&');disp(mean200708de);fprintf('&');disp(std200708ra);fprintf('&');disp(std200708de);fprintf('\\')
fprintf('Sep.2007 &');disp(day200709);fprintf('&');disp(sum200709);fprintf('&');disp(mean200709ra);fprintf('&');disp(mean200709de);fprintf('&');disp(std200709ra);fprintf('&');disp(std200709de);fprintf('\\')
fprintf('Aug.2008 &');disp(day200808);fprintf('&');disp(sum200808);fprintf('&');disp(mean200808ra);fprintf('&');disp(mean200808de);fprintf('&');disp(std200808ra);fprintf('&');disp(std200808de);fprintf('\\')
fprintf('Sep.2008 &');disp(day200809);fprintf('&');disp(sum200809);fprintf('&');disp(mean200809ra);fprintf('&');disp(mean200809de);fprintf('&');disp(std200809ra);fprintf('&');disp(std200809de);fprintf('\\')
fprintf('Sep.2009 &');disp(day200908);fprintf('&');disp(sum200908);fprintf('&');disp(mean200908ra);fprintf('&');disp(mean200908de);fprintf('&');disp(std200908ra);fprintf('&');disp(std200908de);fprintf('\\')
fprintf('Aug.2010 &');disp(day201008);fprintf('&');disp(sum201008);fprintf('&');disp(mean201008ra);fprintf('&');disp(mean201008de);fprintf('&');disp(std201008ra);fprintf('&');disp(std201008de);fprintf('\\')
fprintf('Sep.2010 &');disp(day201009);fprintf('&');disp(sum201009);fprintf('&');disp(mean201009ra);fprintf('&');disp(mean201009de);fprintf('&');disp(std201009ra);fprintf('&');disp(std201009de);fprintf('\\')
fprintf('Sep.2011 &');disp(day201109);fprintf('&');disp(sum201109);fprintf('&');disp(mean201109ra);fprintf('&');disp(mean201109de);fprintf('&');disp(std201109ra);fprintf('&');disp(std201109de);fprintf('\\')
fprintf('Sep.2014 &');disp(day201409);fprintf('&');disp(sum201409);fprintf('&');disp(mean201409ra);fprintf('&');disp(mean201409de);fprintf('&');disp(std201409ra);fprintf('&');disp(std201409de);fprintf('\\')
